"""Decoder for House Scan Margin journals (HSMJ versions 1 and 2)."""

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
NOTE = 0x07

POS_V1_SIZE = 16
# hsmj.h is packed: these are the sizes of the fields in the C structs.
POS_V2_SIZE = 10
OPT_V2_SIZE = 18
COMBO_PREFIX_SIZE = 8
COMBO_LEG_SIZE = 6
VOID_SIZE = 12


def _crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def _product(raw: bytes) -> str | None:
    try:
        product = raw.decode("ascii")
    except UnicodeDecodeError:
        return None
    if len(product) != 2 or not product.isalpha():
        return None
    return product


def _month_from_code(raw: bytes) -> tuple[int, int] | None:
    code = int.from_bytes(raw, "little")
    month = code & 0x0F
    year = 2000 + (code >> 4)
    if not 1 <= month <= 12:
        return None
    return year, month


def _packed_qty(raw: bytes) -> Decimal | None:
    packed = int.from_bytes(raw, "big")
    negative = bool(packed & 0x80000000)
    scale = (packed >> 24) & 0x7F
    if scale > 15:
        return None
    mantissa = packed & 0x00FFFFFF
    qty = Decimal(mantissa).scaleb(scale - 4)
    return -qty if negative else qty


def _strike(raw: bytes) -> str | None:
    digits: list[int] = []
    for byte in raw:
        hi, lo = byte >> 4, byte & 0x0F
        if hi > 9 or lo > 9:
            return None
        digits.extend((hi, lo))
    value = 0
    for digit in digits:
        value = value * 10 + digit
    return f"{value // 100}.{value % 100:02d}"


def _future_id(product_raw: bytes, month_raw: bytes) -> str | None:
    product = _product(product_raw)
    ym = _month_from_code(month_raw)
    if product is None or ym is None:
        return None
    year, month = ym
    return f"{product}-{year:04d}-{month:02d}"


def _option_id(
    product_raw: bytes, month_raw: bytes, cp_raw: int, strike_raw: bytes
) -> str | None:
    future = _future_id(product_raw, month_raw)
    strike = _strike(strike_raw)
    if future is None or strike is None or cp_raw not in (ord("C"), ord("P")):
        return None
    return f"{future}-{chr(cp_raw)}-{strike}"


def _decode_pos_v1(record: bytes) -> tuple[str, Decimal] | None:
    product = _product(record[0:2])
    try:
        yy = record[2:4].decode("ascii")
        year = 2000 + int(yy)
    except (UnicodeDecodeError, ValueError):
        return None
    letter = chr(record[4])
    qty_cents = int.from_bytes(record[8:12], "little", signed=True)
    side = record[12]
    if (
        product is None
        or not (len(yy) == 2 and yy.isdigit())
        or letter not in MONTH_LETTERS
        or qty_cents < 0
        or side not in (0, 1)
    ):
        return None
    month = MONTH_LETTERS.index(letter) + 1
    qty = Decimal(qty_cents).scaleb(-2)
    if side == 1:
        qty = -qty
    return f"{product}-{year:04d}-{month:02d}", qty


def _decode_pos_v2(record: bytes) -> tuple[str, Decimal] | None:
    instrument_id = _future_id(record[0:2], record[2:4])
    qty = _packed_qty(record[4:8])
    if instrument_id is None or qty is None or record[8] != 0:
        return None
    return instrument_id, qty


def _decode_opt_v2(record: bytes) -> tuple[str, Decimal] | None:
    instrument_id = _option_id(record[0:2], record[2:4], record[4], record[5:8])
    qty = _packed_qty(record[8:12])
    if instrument_id is None or qty is None:
        return None
    return instrument_id, qty


def _apply_fixed_records(
    payload: bytes,
    size: int,
    decoder,
    positions: defaultdict[str, Decimal],
    *,
    replace: bool = False,
) -> None:
    for offset in range(0, len(payload) - size + 1, size):
        decoded = decoder(payload[offset : offset + size])
        if decoded is None:
            continue
        instrument_id, qty = decoded
        if replace:
            positions[instrument_id] = qty
        else:
            positions[instrument_id] += qty


def _apply_combos(payload: bytes, positions: defaultdict[str, Decimal]) -> None:
    offset = 0
    while offset + COMBO_PREFIX_SIZE <= len(payload):
        prefix = payload[offset : offset + COMBO_PREFIX_SIZE]
        n_legs = prefix[4]
        record_size = COMBO_PREFIX_SIZE + n_legs * COMBO_LEG_SIZE
        if offset + record_size > len(payload):
            break

        qty = _packed_qty(prefix[0:4])
        legs: list[tuple[str, int]] = []
        valid = qty is not None
        leg_offset = offset + COMBO_PREFIX_SIZE
        for _ in range(n_legs):
            leg = payload[leg_offset : leg_offset + COMBO_LEG_SIZE]
            instrument_id = _future_id(leg[0:2], leg[2:4])
            ratio = int.from_bytes(leg[4:6], "big", signed=True)
            if instrument_id is None:
                valid = False
            else:
                legs.append((instrument_id, ratio))
            leg_offset += COMBO_LEG_SIZE

        if valid and qty is not None:
            for instrument_id, ratio in legs:
                positions[instrument_id] += qty * ratio
        offset += record_size


def _apply_voids(payload: bytes, positions: defaultdict[str, Decimal]) -> None:
    for offset in range(0, len(payload) - VOID_SIZE + 1, VOID_SIZE):
        record = payload[offset : offset + VOID_SIZE]
        if record[0] == 0:
            instrument_id = _future_id(record[1:3], record[3:5])
        elif record[0] == 1:
            instrument_id = _option_id(record[1:3], record[3:5], record[5], record[6:9])
        else:
            instrument_id = None
        if instrument_id is not None:
            positions[instrument_id] = Decimal(0)


def load_journal(path: str | Path) -> dict:
    """Decode an HSMJ file and return its fully applied, net position book."""

    raw = Path(path).read_bytes()
    if len(raw) < 16 or raw[:4] != b"HSMJ":
        raise ValueError("not an HSMJ file")
    version, n_chunks, _created, hdr_crc = struct.unpack_from("<HHII", raw, 4)
    if _crc32(raw[:12]) != hdr_crc:
        raise ValueError("bad HSMJ header CRC")
    if version not in (1, 2):
        raise ValueError(f"unsupported HSMJ version: {version}")

    positions: defaultdict[str, Decimal] = defaultdict(Decimal)
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
            _apply_fixed_records(payload, POS_V1_SIZE, _decode_pos_v1, positions)
        elif typ == POS_V2:
            _apply_fixed_records(payload, POS_V2_SIZE, _decode_pos_v2, positions)
        elif typ == OPT_V2:
            _apply_fixed_records(payload, OPT_V2_SIZE, _decode_opt_v2, positions)
        elif typ == COMBO:
            _apply_combos(payload, positions)
        elif typ == VOID:
            _apply_voids(payload, positions)
        elif typ == PATCH:
            if flags & 1:
                _apply_fixed_records(
                    payload, OPT_V2_SIZE, _decode_opt_v2, positions, replace=True
                )
            else:
                _apply_fixed_records(
                    payload, POS_V2_SIZE, _decode_pos_v2, positions, replace=True
                )
        # NOTE and unknown chunk types are deliberately ignored.

    return {
        "positions": [
            {"instrument_id": instrument_id, "qty": float(qty)}
            for instrument_id, qty in sorted(positions.items())
            if qty != 0
        ]
    }
