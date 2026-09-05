"""Reader for House Scan Margin journals (HSMJ versions 1 and 2)."""

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

# These sizes come from the packed structures in journal/hsmj.h. In
# particular, hsmj_pos_v2 and hsmj_opt_v2 are 10 and 18 bytes; the stale
# comments that call them 12 and 20 do not add fields to the wire layout.
POS_V1_SIZE = 16
POS_V2_SIZE = 10
OPT_V2_SIZE = 18
COMBO_PREFIX_SIZE = 8
COMBO_LEG_SIZE = 6
VOID_SIZE = 12


def _crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def _product(raw: bytes) -> str | None:
    try:
        value = raw.decode("ascii")
    except UnicodeDecodeError:
        return None
    if len(value) != 2 or not value.isalpha() or not value.isupper():
        return None
    return value


def _month_from_code(raw: bytes) -> tuple[int, int] | None:
    code = int.from_bytes(raw, "little")
    month = code & 0x0F
    if not 1 <= month <= 12:
        return None
    return 2000 + (code >> 4), month


def _packed_qty(raw: bytes) -> Decimal | None:
    word = int.from_bytes(raw, "big")
    scale = (word >> 24) & 0x7F
    if scale > 15:
        return None
    mantissa = word & 0xFFFFFF
    qty = Decimal(mantissa).scaleb(scale - 4)
    return -qty if word & 0x80000000 else qty


def _strike(raw: bytes) -> str | None:
    digits: list[str] = []
    for byte in raw:
        hi, lo = byte >> 4, byte & 0x0F
        if hi > 9 or lo > 9:
            return None
        digits.extend((str(hi), str(lo)))
    text = "".join(digits)
    return f"{int(text[:-2])}.{text[-2:]}"


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
    if future is None or cp_raw not in (ord("C"), ord("P")) or strike is None:
        return None
    return f"{future}-{chr(cp_raw)}-{strike}"


def _decode_pos_v1(record: bytes) -> tuple[str, Decimal] | None:
    product = _product(record[0:2])
    try:
        yy = record[2:4].decode("ascii")
    except UnicodeDecodeError:
        return None
    letter = chr(record[4])
    qty_cents = struct.unpack_from("<i", record, 8)[0]
    side = record[12]
    if (
        product is None
        or len(yy) != 2
        or not yy.isdigit()
        or letter not in MONTH_LETTERS
        or qty_cents < 0
        or side not in (0, 1)
    ):
        return None
    year = 2000 + int(yy)
    month = MONTH_LETTERS.index(letter) + 1
    qty = Decimal(qty_cents).scaleb(-2)
    if side == 1:
        qty = -qty
    return f"{product}-{year:04d}-{month:02d}", qty


def _decode_pos_v2(record: bytes) -> tuple[str, Decimal] | None:
    iid = _future_id(record[0:2], record[2:4])
    qty = _packed_qty(record[4:8])
    if iid is None or qty is None or record[8] != 0:
        return None
    return iid, qty


def _decode_opt_v2(record: bytes) -> tuple[str, Decimal] | None:
    iid = _option_id(record[0:2], record[2:4], record[4], record[5:8])
    qty = _packed_qty(record[8:12])
    if iid is None or qty is None:
        return None
    return iid, qty


def _decode_void(record: bytes) -> str | None:
    kind = record[0]
    if kind == 0:
        return _future_id(record[1:3], record[3:5])
    if kind == 1:
        return _option_id(record[1:3], record[3:5], record[5], record[6:9])
    return None


def _fixed_records(payload: bytes, size: int):
    for offset in range(0, len(payload) - size + 1, size):
        yield payload[offset : offset + size]


def load_journal(path: str | Path) -> dict:
    """Decode a journal and apply its blotter operations in file order."""

    raw = Path(path).read_bytes()
    if len(raw) < 16 or raw[:4] != b"HSMJ":
        raise ValueError("not an HSMJ file")

    version, n_chunks, _created, header_crc = struct.unpack_from("<HHII", raw, 4)
    if _crc32(raw[:12]) != header_crc:
        raise ValueError("bad HSMJ header CRC")
    if version not in (1, 2):
        raise ValueError(f"unsupported HSMJ version: {version}")

    positions: dict[str, Decimal] = defaultdict(Decimal)
    offset = 16
    length_order = "little" if version == 1 else "big"

    for _ in range(n_chunks):
        if offset + 4 > len(raw):
            break
        prefix = raw[offset : offset + 4]
        chunk_type, flags = prefix[0], prefix[1]
        payload_size = int.from_bytes(prefix[2:4], length_order)
        payload_end = offset + 4 + payload_size
        frame_end = payload_end + 4
        if frame_end > len(raw):
            break

        payload = raw[offset + 4 : payload_end]
        stored_crc = int.from_bytes(raw[payload_end:frame_end], "little")
        offset = frame_end
        if _crc32(prefix + payload) != stored_crc:
            continue

        if chunk_type == POS_V1:
            for record in _fixed_records(payload, POS_V1_SIZE):
                decoded = _decode_pos_v1(record)
                if decoded is not None:
                    iid, qty = decoded
                    positions[iid] += qty
        elif chunk_type == POS_V2:
            for record in _fixed_records(payload, POS_V2_SIZE):
                decoded = _decode_pos_v2(record)
                if decoded is not None:
                    iid, qty = decoded
                    positions[iid] += qty
        elif chunk_type == OPT_V2:
            for record in _fixed_records(payload, OPT_V2_SIZE):
                decoded = _decode_opt_v2(record)
                if decoded is not None:
                    iid, qty = decoded
                    positions[iid] += qty
        elif chunk_type == COMBO:
            record_offset = 0
            while record_offset + COMBO_PREFIX_SIZE <= len(payload):
                prefix_end = record_offset + COMBO_PREFIX_SIZE
                packed = _packed_qty(payload[record_offset : record_offset + 4])
                leg_count = payload[record_offset + 4]
                record_end = prefix_end + leg_count * COMBO_LEG_SIZE
                if record_end > len(payload):
                    break

                legs: list[tuple[str, int]] = []
                for leg_offset in range(prefix_end, record_end, COMBO_LEG_SIZE):
                    leg = payload[leg_offset : leg_offset + COMBO_LEG_SIZE]
                    iid = _future_id(leg[0:2], leg[2:4])
                    ratio = int.from_bytes(leg[4:6], "big", signed=True)
                    if iid is None:
                        legs = []
                        break
                    legs.append((iid, ratio))
                if packed is not None and len(legs) == leg_count:
                    for iid, ratio in legs:
                        positions[iid] += packed * ratio
                record_offset = record_end
        elif chunk_type == VOID:
            for record in _fixed_records(payload, VOID_SIZE):
                iid = _decode_void(record)
                if iid is not None:
                    positions.pop(iid, None)
        elif chunk_type == PATCH:
            if flags & 1:
                records = _fixed_records(payload, OPT_V2_SIZE)
                decoder = _decode_opt_v2
            else:
                records = _fixed_records(payload, POS_V2_SIZE)
                decoder = _decode_pos_v2
            for record in records:
                decoded = decoder(record)
                if decoded is not None:
                    iid, qty = decoded
                    if qty == 0:
                        positions.pop(iid, None)
                    else:
                        positions[iid] = qty

    return {
        "positions": [
            {"instrument_id": iid, "qty": float(qty)}
            for iid, qty in positions.items()
            if qty != 0
        ]
    }
