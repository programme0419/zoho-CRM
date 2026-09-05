"""Reader for the House Scan Margin Journal (HSMJ) wire format."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
import struct
import zlib
from pathlib import Path
from typing import Callable, TypeVar


MONTH_LETTERS = "FGHJKMNQUVXZ"
KNOWN_PRODUCTS = {"CL", "HO", "RB", "ES", "GX"}

POS_V1 = 0x01
POS_V2 = 0x02
OPT_V2 = 0x03
COMBO = 0x04
VOID = 0x05
PATCH = 0x06

T = TypeVar("T")


def _crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def _product(raw: bytes) -> str | None:
    try:
        value = raw.decode("ascii")
    except UnicodeDecodeError:
        return None
    return value if value in KNOWN_PRODUCTS else None


def _month(raw: bytes) -> tuple[int, int] | None:
    code = int.from_bytes(raw, "little")
    month = code & 0x0F
    if not 1 <= month <= 12:
        return None
    return 2000 + (code >> 4), month


def _packed_qty(raw: bytes) -> Decimal | None:
    packed = int.from_bytes(raw, "big")
    sign = -1 if packed & 0x80000000 else 1
    scale = (packed >> 24) & 0x7F
    if scale > 15:
        return None
    mantissa = packed & 0x00FFFFFF
    return Decimal(sign * mantissa).scaleb(scale - 4)


def _strike(raw: bytes) -> str | None:
    digits: list[str] = []
    for byte in raw:
        hi, lo = byte >> 4, byte & 0x0F
        if hi > 9 or lo > 9:
            return None
        digits.extend((str(hi), str(lo)))
    whole = "".join(digits[:-2]).lstrip("0") or "0"
    return f"{whole}.{''.join(digits[-2:])}"


def _future_id(product: str, month: tuple[int, int]) -> str:
    return f"{product}-{month[0]:04d}-{month[1]:02d}"


def _option_id(product: str, month: tuple[int, int], cp: str, strike: str) -> str:
    return f"{_future_id(product, month)}-{cp}-{strike}"


def _decode_pos_v1(rec: bytes) -> tuple[str, Decimal] | None:
    product = _product(rec[0:2])
    try:
        yy = rec[2:4].decode("ascii")
        year = 2000 + int(yy) if len(yy) == 2 and yy.isdigit() else -1
        letter = chr(rec[4])
    except (UnicodeDecodeError, ValueError):
        return None
    qty_cents = int.from_bytes(rec[8:12], "little", signed=True)
    side = rec[12]
    if product is None or year < 2000 or letter not in MONTH_LETTERS or qty_cents < 0 or side not in (0, 1):
        return None
    qty = Decimal(qty_cents).scaleb(-2)
    if side:
        qty = -qty
    return _future_id(product, (year, MONTH_LETTERS.index(letter) + 1)), qty


def _decode_pos_v2(rec: bytes) -> tuple[str, Decimal] | None:
    product = _product(rec[0:2])
    month = _month(rec[2:4])
    qty = _packed_qty(rec[4:8])
    if product is None or month is None or qty is None or rec[8] != 0:
        return None
    return _future_id(product, month), qty


def _decode_opt_v2(rec: bytes) -> tuple[str, Decimal] | None:
    product = _product(rec[0:2])
    month = _month(rec[2:4])
    try:
        cp = chr(rec[4])
    except ValueError:
        return None
    strike = _strike(rec[5:8])
    qty = _packed_qty(rec[8:12])
    if product is None or month is None or cp not in ("C", "P") or strike is None or qty is None:
        return None
    return _option_id(product, month, cp, strike), qty


def _decode_void(rec: bytes) -> str | None:
    kind = rec[0]
    product = _product(rec[1:3])
    month = _month(rec[3:5])
    if product is None or month is None:
        return None
    if kind == 0:
        return _future_id(product, month)
    if kind != 1:
        return None
    try:
        cp = chr(rec[5])
    except ValueError:
        return None
    strike = _strike(rec[6:9])
    if cp not in ("C", "P") or strike is None:
        return None
    return _option_id(product, month, cp, strike)


def _fixed_records(payload: bytes, sizes: tuple[int, ...], decoder: Callable[[bytes], T | None]) -> list[T]:
    """Decode either the packed C size or the documented padded size.

    hsmj.h's packed field totals are 10/18 bytes for v2 futures/options,
    while adjacent comments call those records 12/20 bytes. House tapes
    exist in both forms. Scoring complete valid records distinguishes them.
    """

    best: list[T] = []
    best_score: tuple[int, int, int, int] | None = None
    for preference, size in enumerate(sizes):
        slots = len(payload) // size
        decoded: list[T] = []
        invalid = 0
        for offset in range(0, slots * size, size):
            item = decoder(payload[offset : offset + size])
            if item is None:
                invalid += 1
            else:
                decoded.append(item)
        score = (len(decoded) * size, -invalid, -(len(payload) % size), -preference)
        if best_score is None or score > best_score:
            best_score, best = score, decoded
    return best


def _apply_combo(payload: bytes, add: Callable[[str, Decimal], None]) -> None:
    offset = 0
    while offset + 8 <= len(payload):
        qty = _packed_qty(payload[offset : offset + 4])
        n_legs = payload[offset + 4]
        record_size = 8 + n_legs * 6
        if offset + record_size > len(payload):
            break
        legs: list[tuple[str, int]] = []
        valid = qty is not None and n_legs > 0
        for leg_offset in range(offset + 8, offset + record_size, 6):
            product = _product(payload[leg_offset : leg_offset + 2])
            month = _month(payload[leg_offset + 2 : leg_offset + 4])
            ratio = int.from_bytes(payload[leg_offset + 4 : leg_offset + 6], "big", signed=True)
            if product is None or month is None:
                valid = False
            else:
                legs.append((_future_id(product, month), ratio))
        if valid and qty is not None:
            for instrument_id, ratio in legs:
                add(instrument_id, qty * ratio)
        offset += record_size


def load_journal(path: str | Path) -> dict:
    raw = Path(path).read_bytes()
    if len(raw) < 16 or raw[:4] != b"HSMJ":
        raise ValueError("not an HSMJ file")
    version, n_chunks, _created, header_crc = struct.unpack_from("<HHII", raw, 4)
    if _crc32(raw[:12]) != header_crc:
        raise ValueError("bad HSMJ header CRC")
    if version not in (1, 2):
        raise ValueError(f"unsupported HSMJ version: {version}")

    book: dict[str, Decimal] = defaultdict(Decimal)

    def add(instrument_id: str, qty: Decimal) -> None:
        book[instrument_id] += qty

    offset = 16
    for _ in range(n_chunks):
        if offset + 8 > len(raw):
            break
        prefix = raw[offset : offset + 4]
        typ, flags = prefix[0], prefix[1]
        nbytes = int.from_bytes(prefix[2:4], "little" if version == 1 else "big")
        end = offset + 4 + nbytes
        if end + 4 > len(raw):
            break
        payload = raw[offset + 4 : end]
        stored_crc = int.from_bytes(raw[end : end + 4], "little")
        offset = end + 4
        if _crc32(prefix + payload) != stored_crc:
            continue

        if typ == POS_V1:
            for item in _fixed_records(payload, (16,), _decode_pos_v1):
                add(*item)
        elif typ == POS_V2:
            for item in _fixed_records(payload, (10, 12), _decode_pos_v2):
                add(*item)
        elif typ == OPT_V2:
            for item in _fixed_records(payload, (18, 20), _decode_opt_v2):
                add(*item)
        elif typ == COMBO:
            _apply_combo(payload, add)
        elif typ == VOID:
            for instrument_id in _fixed_records(payload, (12,), _decode_void):
                book.pop(instrument_id, None)
        elif typ == PATCH:
            decoder = _decode_opt_v2 if flags & 1 else _decode_pos_v2
            sizes = (18, 20) if flags & 1 else (10, 12)
            for instrument_id, qty in _fixed_records(payload, sizes, decoder):
                if qty == 0:
                    book.pop(instrument_id, None)
                else:
                    book[instrument_id] = qty

    positions = [
        {"instrument_id": instrument_id, "qty": float(qty)}
        for instrument_id, qty in book.items()
        if qty != 0
    ]
    return {"positions": positions}
