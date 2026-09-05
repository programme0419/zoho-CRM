"""Decoder for House Scan Margin Journal (HSMJ) blotter files."""

from __future__ import annotations

import struct
import zlib
from collections import defaultdict
from decimal import Decimal
from pathlib import Path


MONTH_LETTERS = "FGHJKMNQUVXZ"

POS_V1 = 0x01
POS_V2 = 0x02
OPT_V2 = 0x03
COMBO = 0x04
VOID = 0x05
PATCH = 0x06

POS_V1_SIZE = 16
# These are packed C structures. The prose comments in hsmj.h that call
# them 12 and 20 bytes include stale sizes; the declared on-wire fields are
# 10 and 18 bytes respectively.
POS_V2_SIZE = 10
OPT_V2_SIZE = 18
VOID_SIZE = 12
COMBO_PREFIX_SIZE = 8
COMBO_LEG_SIZE = 6


def _crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def _product(raw: bytes) -> str | None:
    try:
        product = raw.decode("ascii")
    except UnicodeDecodeError:
        return None
    return product if len(product) == 2 else None


def _v1_month(yy_raw: bytes, letter_byte: int) -> tuple[int, int] | None:
    try:
        yy = yy_raw.decode("ascii")
        if len(yy) != 2 or not yy.isdigit():
            return None
        letter = chr(letter_byte)
    except (UnicodeDecodeError, ValueError):
        return None
    if letter not in MONTH_LETTERS:
        return None
    return 2000 + int(yy), MONTH_LETTERS.index(letter) + 1


def _v2_month(raw: bytes) -> tuple[int, int] | None:
    code = int.from_bytes(raw, "little")
    month = code & 0x0F
    if month < 1 or month > 12:
        return None
    return 2000 + (code >> 4), month


def _packed_qty(raw: bytes) -> Decimal | None:
    packed = int.from_bytes(raw, "big")
    scale = (packed >> 24) & 0x7F
    if scale > 15:
        return None
    mantissa = packed & 0xFFFFFF
    qty = Decimal(mantissa).scaleb(scale - 4)
    return -qty if packed & 0x80000000 else qty


def _strike(raw: bytes) -> str | None:
    digits: list[str] = []
    for byte in raw:
        high, low = byte >> 4, byte & 0x0F
        if high > 9 or low > 9:
            return None
        digits.extend((str(high), str(low)))
    cents = int("".join(digits))
    return f"{cents // 100}.{cents % 100:02d}"


def _future_id(product: str, month: tuple[int, int]) -> str:
    year, mon = month
    return f"{product}-{year:04d}-{mon:02d}"


def _option_id(
    product: str, month: tuple[int, int], cp_byte: int, strike_raw: bytes
) -> str | None:
    if cp_byte not in (ord("C"), ord("P")):
        return None
    strike = _strike(strike_raw)
    if strike is None:
        return None
    return f"{_future_id(product, month)}-{chr(cp_byte)}-{strike}"


def _decode_pos_v2(record: bytes) -> tuple[str, Decimal] | None:
    product = _product(record[0:2])
    month = _v2_month(record[2:4])
    qty = _packed_qty(record[4:8])
    if product is None or month is None or qty is None or record[8] != 0:
        return None
    return _future_id(product, month), qty


def _decode_opt_v2(record: bytes) -> tuple[str, Decimal] | None:
    product = _product(record[0:2])
    month = _v2_month(record[2:4])
    qty = _packed_qty(record[8:12])
    if product is None or month is None or qty is None:
        return None
    iid = _option_id(product, month, record[4], record[5:8])
    if iid is None:
        return None
    return iid, qty


def _walk_fixed(payload: bytes, size: int):
    for offset in range(0, len(payload) - size + 1, size):
        yield payload[offset : offset + size]


def _apply_pos_v1(payload: bytes, book: dict[str, Decimal]) -> None:
    for record in _walk_fixed(payload, POS_V1_SIZE):
        product = _product(record[0:2])
        month = _v1_month(record[2:4], record[4])
        qty_cents = int.from_bytes(record[8:12], "little", signed=True)
        side = record[12]
        if product is None or month is None or qty_cents < 0 or side not in (0, 1):
            continue
        qty = Decimal(qty_cents).scaleb(-2)
        if side == 1:
            qty = -qty
        book[_future_id(product, month)] += qty


def _apply_pos_v2(payload: bytes, book: dict[str, Decimal]) -> None:
    for record in _walk_fixed(payload, POS_V2_SIZE):
        decoded = _decode_pos_v2(record)
        if decoded is not None:
            iid, qty = decoded
            book[iid] += qty


def _apply_opt_v2(payload: bytes, book: dict[str, Decimal]) -> None:
    for record in _walk_fixed(payload, OPT_V2_SIZE):
        decoded = _decode_opt_v2(record)
        if decoded is not None:
            iid, qty = decoded
            book[iid] += qty


def _apply_combo(payload: bytes, book: dict[str, Decimal]) -> None:
    offset = 0
    while offset + COMBO_PREFIX_SIZE <= len(payload):
        prefix = payload[offset : offset + COMBO_PREFIX_SIZE]
        n_legs = prefix[4]
        size = COMBO_PREFIX_SIZE + n_legs * COMBO_LEG_SIZE
        if offset + size > len(payload):
            break
        qty = _packed_qty(prefix[0:4])
        legs: list[tuple[str, int]] = []
        valid = qty is not None
        for index in range(n_legs):
            start = offset + COMBO_PREFIX_SIZE + index * COMBO_LEG_SIZE
            leg = payload[start : start + COMBO_LEG_SIZE]
            product = _product(leg[0:2])
            month = _v2_month(leg[2:4])
            ratio = int.from_bytes(leg[4:6], "big", signed=True)
            if product is None or month is None:
                valid = False
            else:
                legs.append((_future_id(product, month), ratio))
        if valid and qty is not None:
            for iid, ratio in legs:
                book[iid] += qty * ratio
        offset += size


def _decode_void(record: bytes) -> str | None:
    kind = record[0]
    product = _product(record[1:3])
    month = _v2_month(record[3:5])
    if product is None or month is None:
        return None
    if kind == 0:
        return _future_id(product, month)
    if kind == 1:
        return _option_id(product, month, record[5], record[6:9])
    return None


def _apply_void(payload: bytes, book: dict[str, Decimal]) -> None:
    for record in _walk_fixed(payload, VOID_SIZE):
        iid = _decode_void(record)
        if iid is not None:
            book[iid] = Decimal(0)


def _apply_patch(payload: bytes, flags: int, book: dict[str, Decimal]) -> None:
    option = bool(flags & 1)
    size = OPT_V2_SIZE if option else POS_V2_SIZE
    decoder = _decode_opt_v2 if option else _decode_pos_v2
    for record in _walk_fixed(payload, size):
        decoded = decoder(record)
        if decoded is not None:
            iid, qty = decoded
            book[iid] = qty


def load_journal(path: str | Path) -> dict:
    """Decode an HSMJ file and return its final, net blotter positions."""

    raw = Path(path).read_bytes()
    if len(raw) < 16 or raw[:4] != b"HSMJ":
        raise ValueError("not an HSMJ file")
    version, n_chunks, _created, hdr_crc = struct.unpack_from("<HHII", raw, 4)
    if _crc32(raw[:12]) != hdr_crc:
        raise ValueError("bad HSMJ header CRC")
    if version not in (1, 2):
        raise ValueError(f"unsupported HSMJ version: {version}")

    book: dict[str, Decimal] = defaultdict(Decimal)
    offset = 16
    for _ in range(n_chunks):
        if offset + 4 > len(raw):
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
            _apply_pos_v1(payload, book)
        elif typ == POS_V2:
            _apply_pos_v2(payload, book)
        elif typ == OPT_V2:
            _apply_opt_v2(payload, book)
        elif typ == COMBO:
            _apply_combo(payload, book)
        elif typ == VOID:
            _apply_void(payload, book)
        elif typ == PATCH:
            _apply_patch(payload, flags, book)

    return {
        "positions": [
            {"instrument_id": iid, "qty": qty}
            for iid, qty in sorted(book.items())
            if qty != 0
        ]
    }
