"""House Scan Margin engine.

The implementation in this module follows ``docs/methodology.md``.  In
particular, scenario P/L is rounded per net position before it is aggregated,
whereas deltas are kept as binary64 values until they are turned into money.
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Any

try:  # Support both ``python hsm/run_margin.py`` and package imports in tests.
    from .lib.black76 import delta as black76_delta
    from .lib.black76 import price as black76_price
    from .lib.black76 import year_fraction
except ImportError:  # pragma: no cover - this is the CLI import path
    from lib.black76 import delta as black76_delta
    from lib.black76 import price as black76_price
    from lib.black76 import year_fraction


CENT = Decimal("0.01")

# Scenario arrays are in scenario-id order.
PRICE_MULT = (
    0.0,
    0.0,
    1.0 / 3.0,
    1.0 / 3.0,
    -1.0 / 3.0,
    -1.0 / 3.0,
    2.0 / 3.0,
    2.0 / 3.0,
    -2.0 / 3.0,
    -2.0 / 3.0,
    1.0,
    1.0,
    -1.0,
    -1.0,
    3.0,
    -3.0,
)
VOL_DIRECTION = (1.0, -1.0) * 7 + (1.0, -1.0)
PL_WEIGHT = (1.0,) * 14 + (0.28, 0.28)

_INSTRUMENT_RE = re.compile(
    r"^(?P<product>.+)-(?P<year>\d{4})-(?P<month>0[1-9]|1[0-2])"
    r"(?:-(?P<kind>[CP])-(?P<strike>-?\d+\.\d{2}))?$"
)

_MONEY_FIELDS = (
    "scanning_risk",
    "intra_charge",
    "inter_credit",
    "nov_credit",
    "som",
    "raw_margin",
    "cc_margin_native",
    "cc_margin_usd",
)


def _decimal(value: Any) -> Decimal:
    """Convert JSON-style numbers without importing binary noise."""

    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def q2(value: Any) -> Decimal:
    return _decimal(value).quantize(CENT, rounding=ROUND_HALF_EVEN)


def money(value: float) -> Decimal:
    """Methodology conversion for one binary64 position-scenario P/L."""

    return Decimal(format(float(value), ".10f")).quantize(
        CENT, rounding=ROUND_HALF_EVEN
    )


def net_positions(portfolio: dict) -> dict[str, float]:
    """Net duplicate rows using the decimal values represented in the input."""

    quantities: dict[str, Decimal] = defaultdict(Decimal)
    for row in portfolio["positions"]:
        quantities[row["instrument_id"]] += _decimal(row["qty"])
    return {
        instrument_id: float(quantity)
        for instrument_id, quantity in quantities.items()
        if quantity != 0
    }


@dataclass(frozen=True)
class Instrument:
    instrument_id: str
    product: str
    bucket: str
    option_kind: str | None
    strike: float | None

    @property
    def is_option(self) -> bool:
        return self.option_kind is not None

    @property
    def underlying_id(self) -> str:
        return f"{self.product}-{self.bucket}"


def parse_instrument(instrument_id: str) -> Instrument:
    match = _INSTRUMENT_RE.fullmatch(instrument_id)
    if match is None:
        raise ValueError(f"invalid instrument_id: {instrument_id!r}")
    bucket = f"{match.group('year')}-{match.group('month')}"
    strike_text = match.group("strike")
    return Instrument(
        instrument_id=instrument_id,
        product=match.group("product"),
        bucket=bucket,
        option_kind=match.group("kind"),
        strike=float(strike_text) if strike_text is not None else None,
    )


def product_of(instrument_id: str) -> str:
    return parse_instrument(instrument_id).product


def is_option(instrument_id: str) -> bool:
    return parse_instrument(instrument_id).is_option


@dataclass
class PositionRisk:
    instrument: Instrument
    quantity: float
    product_config: dict[str, Any]
    scenario_pl: list[Decimal]
    scenario_delta: list[float]
    atm_delta: float
    base_option_value: float


@dataclass(frozen=True)
class CombinedCommodityMeta:
    currency: str
    ics_group: str
    intra_tiers: dict[str, Any]


def _cc_metadata(
    config: dict, included_ccs: set[str] | None = None
) -> dict[str, CombinedCommodityMeta]:
    """Build the CC attributes needed by spreading.

    Multiple products may map to one CC. Currency, ICS group, and intra tier
    rates are CC-level concepts in the methodology, so conflicting values
    cannot define a calculation and are rejected explicitly.
    """

    by_cc: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for product_name, product_config in config["products"].items():
        if (
            included_ccs is not None
            and product_config["cc_id"] not in included_ccs
        ):
            continue
        by_cc[product_config["cc_id"]].append((product_name, product_config))

    result: dict[str, CombinedCommodityMeta] = {}
    for cc_id, product_rows in by_cc.items():
        product_rows.sort(key=lambda item: item[0])
        first = product_rows[0][1]
        currency = first["currency"]
        group = first["ics_group"]
        tiers = first["intra_tiers"]
        for product_name, product_config in product_rows[1:]:
            if (
                product_config["currency"] != currency
                or product_config["ics_group"] != group
                or any(
                    _decimal(product_config["intra_tiers"][tier])
                    != _decimal(tiers[tier])
                    for tier in ("adjacent", "mid", "back")
                )
            ):
                raise ValueError(
                    f"products in cc_id {cc_id!r} have conflicting CC "
                    f"attributes (including product {product_name!r})"
                )
        result[cc_id] = CombinedCommodityMeta(currency, group, tiers)
    return result


def _position_risk(
    instrument: Instrument,
    quantity: float,
    product_config: dict[str, Any],
    market: dict,
    valuation_date: date,
) -> PositionRisk:
    """Price one already-netted position in every scenario."""

    forward = float(market["futures_price"][instrument.underlying_id])
    multiplier = float(product_config["multiplier"])
    psr = float(product_config["price_scan_range"])
    vsf = float(product_config["vol_scan_fraction"])

    if instrument.is_option:
        strike = instrument.strike
        assert strike is not None
        is_call = instrument.option_kind == "C"
        vol = float(market["atm_vol"][instrument.instrument_id])
        expiry = date.fromisoformat(market["option_expiry"][instrument.instrument_id])
        time_to_expiry = year_fraction(valuation_date, expiry)
        base_value = black76_price(forward, strike, vol, time_to_expiry, is_call)
        atm_delta = black76_delta(forward, strike, vol, time_to_expiry, is_call)
    else:
        strike = None
        is_call = False
        vol = 0.0
        time_to_expiry = 0.0
        base_value = 0.0
        atm_delta = 1.0

    scenario_pl: list[Decimal] = []
    scenario_delta: list[float] = []
    for index in range(16):
        shocked_forward_unfloored = forward + PRICE_MULT[index] * psr
        if instrument.is_option:
            # The forward floor applies before option logarithms, not to the
            # linear futures P/L calculation.
            shocked_forward = max(shocked_forward_unfloored, 1e-8)
            shocked_vol = max(
                vol * (1.0 + VOL_DIRECTION[index] * vsf), 1e-6
            )
            assert strike is not None
            shocked_value = black76_price(
                shocked_forward, strike, shocked_vol, time_to_expiry, is_call
            )
            raw_pl = quantity * (shocked_value - base_value) * multiplier
            per_contract_delta = black76_delta(
                shocked_forward, strike, shocked_vol, time_to_expiry, is_call
            )
        else:
            raw_pl = (
                quantity
                * (shocked_forward_unfloored - forward)
                * multiplier
            )
            per_contract_delta = 1.0

        scenario_pl.append(money(raw_pl * PL_WEIGHT[index]))
        scenario_delta.append(per_contract_delta)

    return PositionRisk(
        instrument=instrument,
        quantity=quantity,
        product_config=product_config,
        scenario_pl=scenario_pl,
        scenario_delta=scenario_delta,
        atm_delta=atm_delta,
        base_option_value=base_value,
    )


def _composite_buckets(
    positions: list[PositionRisk],
    cc_scenario_pl: list[Decimal],
    worst_index: int,
) -> dict[str, float]:
    if worst_index < 14:
        next_worst_index = min(
            (index for index in range(14) if index != worst_index),
            key=lambda index: (cc_scenario_pl[index], index),
        )
        delta_indexes = (worst_index, next_worst_index)
    else:
        delta_indexes = (worst_index,)

    buckets: dict[str, float] = defaultdict(float)
    for position in positions:
        if len(delta_indexes) == 2:
            per_contract = (
                position.scenario_delta[delta_indexes[0]]
                + position.scenario_delta[delta_indexes[1]]
            ) / 2.0
        else:
            per_contract = position.scenario_delta[delta_indexes[0]]
        buckets[position.instrument.bucket] += per_contract * position.quantity
    return dict(buckets)


def _bucket_date(bucket: str) -> date:
    return date.fromisoformat(f"{bucket}-01")


def _opposite_sign(left: float, right: float) -> bool:
    return (left > 0.0 and right < 0.0) or (left < 0.0 and right > 0.0)


def _intra_spread(
    bucket_deltas: dict[str, float], tiers: dict[str, Any]
) -> tuple[Decimal, float]:
    remaining = dict(bucket_deltas)
    charges = Decimal("0")

    while True:
        nonzero = [bucket for bucket, value in remaining.items() if value != 0.0]
        if not nonzero:
            break
        bucket_a = min(nonzero, key=lambda bucket: (-abs(remaining[bucket]), bucket))
        candidates = [
            bucket
            for bucket in nonzero
            if _opposite_sign(remaining[bucket_a], remaining[bucket])
        ]
        if not candidates:
            break

        date_a = _bucket_date(bucket_a)
        bucket_b = min(
            candidates,
            key=lambda bucket: (
                abs((_bucket_date(bucket) - date_a).days),
                -abs(remaining[bucket]),
                bucket,
            ),
        )
        day_count = abs((_bucket_date(bucket_b) - date_a).days)
        paired_delta = min(abs(remaining[bucket_a]), abs(remaining[bucket_b]))

        if day_count <= 32:
            rate = _decimal(tiers["adjacent"])
        elif day_count <= 125:
            rate = _decimal(tiers["mid"])
        else:
            rate = _decimal(tiers["back"])
        charges += (
            _decimal(paired_delta)
            * rate
            * _decimal(math.sqrt(day_count / 365.0))
        )

        sign_a = 1.0 if remaining[bucket_a] > 0.0 else -1.0
        sign_b = 1.0 if remaining[bucket_b] > 0.0 else -1.0
        remaining[bucket_a] -= sign_a * paired_delta
        remaining[bucket_b] -= sign_b * paired_delta

    return q2(charges), sum(remaining.values())


def _som(positions: list[PositionRisk]) -> Decimal:
    total = Decimal("0")
    for position in positions:
        if not position.instrument.is_option or position.quantity >= 0.0:
            continue
        factor = 1.0 + max(0.0, 0.25 - abs(position.atm_delta))
        contribution = (
            float(position.product_config["som_rate"])
            * abs(position.quantity)
            * factor
        )
        total += _decimal(contribution)
    return q2(total)


def _nov_credit(positions: list[PositionRisk]) -> Decimal:
    total = Decimal("0")
    for position in positions:
        if (
            not position.instrument.is_option
            or position.quantity <= 0.0
            or abs(position.atm_delta) >= 0.35
        ):
            continue
        contribution = max(
            0.0,
            position.quantity
            * position.base_option_value
            * float(position.product_config["multiplier"]),
        )
        total += _decimal(contribution)
    return q2(total)


def _inter_commodity_credits(
    config: dict,
    metadata: dict[str, CombinedCommodityMeta],
    outright_deltas: dict[str, float],
) -> dict[str, Decimal]:
    residuals = dict(outright_deltas)
    credits: dict[str, Decimal] = {
        cc_id: Decimal("0") for cc_id in outright_deltas
    }

    for spread in sorted(config["inter_spreads"], key=lambda row: row["priority"]):
        cc_a = spread["leg_a"]
        cc_b = spread["leg_b"]
        if (
            cc_a not in residuals
            or cc_b not in residuals
            or cc_a not in metadata
            or cc_b not in metadata
        ):
            continue
        meta_a = metadata[cc_a]
        meta_b = metadata[cc_b]
        if (
            meta_a.ics_group != meta_b.ics_group
            or meta_a.ics_group != spread["ics_group"]
            or meta_a.currency != meta_b.currency
        ):
            continue

        ratio_a = float(spread["ratio_a"])
        ratio_b = float(spread["ratio_b"])
        if ratio_a <= 0.0 or ratio_b <= 0.0:
            # Ratios are necessarily positive for "reduce ... toward zero" to
            # be defined. A malformed pair cannot contribute a credit.
            continue
        delta_a = residuals[cc_a]
        delta_b = residuals[cc_b]
        if delta_a == 0.0 or delta_b == 0.0:
            continue
        units_a = delta_a / ratio_a
        units_b = delta_b / ratio_b
        if not _opposite_sign(units_a, units_b):
            continue

        paired_units = min(abs(units_a), abs(units_b))
        credit = _decimal(paired_units) * _decimal(spread["credit_per_unit"])
        credit_b = q2(credit / 2)
        credit_a = credit - credit_b
        credits[cc_a] += credit_a
        credits[cc_b] += credit_b

        amount_a = paired_units * ratio_a
        amount_b = paired_units * ratio_b
        residuals[cc_a] = max(0.0, delta_a - amount_a) if delta_a > 0 else min(
            0.0, delta_a + amount_a
        )
        residuals[cc_b] = max(0.0, delta_b - amount_b) if delta_b > 0 else min(
            0.0, delta_b + amount_b
        )

    return credits


def compute_report(portfolio: dict, market: dict, config: dict) -> dict:
    net = net_positions(portfolio)
    products = config["products"]
    valuation_date = date.fromisoformat(market["valuation_date"])

    by_cc: dict[str, list[PositionRisk]] = defaultdict(list)
    # Instrument order is not economically meaningful. Sorting also makes the
    # unavoidable binary64 delta additions independent of portfolio row order.
    for instrument_id, quantity in sorted(net.items()):
        instrument = parse_instrument(instrument_id)
        product_config = products[instrument.product]
        cc_id = product_config["cc_id"]
        by_cc[cc_id].append(
            _position_risk(
                instrument,
                quantity,
                product_config,
                market,
                valuation_date,
            )
        )

    metadata = _cc_metadata(config, set(by_cc))

    cc_values: dict[str, dict[str, Any]] = {}
    outright_deltas: dict[str, float] = {}
    for cc_id, positions in by_cc.items():
        cc_scenario_pl = [
            sum((position.scenario_pl[index] for position in positions), Decimal("0"))
            for index in range(16)
        ]
        worst_index = min(
            range(16), key=lambda index: (cc_scenario_pl[index], index)
        )
        scanning_risk = q2(max(Decimal("0"), -cc_scenario_pl[worst_index]))
        buckets = _composite_buckets(positions, cc_scenario_pl, worst_index)
        intra_charge, outright_delta = _intra_spread(
            buckets, metadata[cc_id].intra_tiers
        )
        outright_deltas[cc_id] = outright_delta
        cc_values[cc_id] = {
            "scanning_risk": scanning_risk,
            "intra_charge": intra_charge,
            "nov_credit": _nov_credit(positions),
            "som": _som(positions),
            "worst_scenario_id": worst_index + 1,
        }

    inter_credits = _inter_commodity_credits(config, metadata, outright_deltas)

    fx = {currency: _decimal(rate) for currency, rate in market["fx_to_usd"].items()}
    rows: list[dict[str, Any]] = []
    total = Decimal("0.00")
    for cc_id in sorted(by_cc):
        values = cc_values[cc_id]
        # Pair splitting can retain fractions of a cent on leg A so that the
        # full pair credit is conserved. Use that exact allocated amount in
        # raw margin; the report representation itself is cent-rounded.
        inter_credit_exact = inter_credits[cc_id]
        inter_credit = q2(inter_credit_exact)
        raw_margin = q2(
            values["scanning_risk"]
            + values["intra_charge"]
            - inter_credit_exact
            - values["nov_credit"]
        )
        cc_margin_native = max(raw_margin, values["som"])
        cc_margin_usd = q2(cc_margin_native * fx[metadata[cc_id].currency])
        total += cc_margin_usd
        rows.append(
            {
                "cc_id": cc_id,
                "currency": metadata[cc_id].currency,
                "scanning_risk": float(values["scanning_risk"]),
                "intra_charge": float(values["intra_charge"]),
                "inter_credit": float(inter_credit),
                "nov_credit": float(values["nov_credit"]),
                "som": float(values["som"]),
                "raw_margin": float(raw_margin),
                "cc_margin_native": float(cc_margin_native),
                "cc_margin_usd": float(cc_margin_usd),
                "worst_scenario_id": int(values["worst_scenario_id"]),
            }
        )

    return {
        "valuation_date": market["valuation_date"],
        "currency": "USD",
        "total_margin_usd": float(total),
        "combined_commodities": rows,
    }


def load_json(path: str | Path) -> dict[str, Any]:
    # Retain the exact decimal spelling of JSON non-integers through netting and
    # configuration-money calculations. Pricing explicitly converts to float.
    return json.loads(Path(path).read_text(), parse_float=Decimal)


def _format_money(value: Any) -> str:
    return format(q2(value), ".2f")


def write_report(report: dict, path: str | Path) -> None:
    """Write schema-shaped JSON with money numbers rendered to two decimals."""

    lines = [
        "{",
        f'  "valuation_date": {json.dumps(report["valuation_date"])},',
        f'  "currency": {json.dumps(report["currency"])},',
        f'  "total_margin_usd": {_format_money(report["total_margin_usd"])},',
        '  "combined_commodities": [',
    ]
    rows = report["combined_commodities"]
    for row_index, row in enumerate(rows):
        lines.extend(
            [
                "    {",
                f'      "cc_id": {json.dumps(row["cc_id"])},',
                f'      "currency": {json.dumps(row["currency"])},',
            ]
        )
        for field in _MONEY_FIELDS:
            lines.append(f'      "{field}": {_format_money(row[field])},')
        lines.append(
            f'      "worst_scenario_id": {int(row["worst_scenario_id"])}'
        )
        lines.append("    }" + ("," if row_index + 1 < len(rows) else ""))
    lines.extend(["  ]", "}"])

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n")
