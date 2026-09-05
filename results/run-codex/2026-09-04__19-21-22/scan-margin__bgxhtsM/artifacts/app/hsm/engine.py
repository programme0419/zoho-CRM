"""House Scan Margin calculation engine."""

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

from lib.black76 import delta as black_delta
from lib.black76 import price as black_price
from lib.black76 import year_fraction


CENT = Decimal("0.01")

# (price multiplier, vol direction, weighted-P/L multiplier), in id order.
SCENARIOS: tuple[tuple[float, int, float], ...] = (
    (0.0, 1, 1.0),
    (0.0, -1, 1.0),
    (1.0 / 3.0, 1, 1.0),
    (1.0 / 3.0, -1, 1.0),
    (-1.0 / 3.0, 1, 1.0),
    (-1.0 / 3.0, -1, 1.0),
    (2.0 / 3.0, 1, 1.0),
    (2.0 / 3.0, -1, 1.0),
    (-2.0 / 3.0, 1, 1.0),
    (-2.0 / 3.0, -1, 1.0),
    (1.0, 1, 1.0),
    (1.0, -1, 1.0),
    (-1.0, 1, 1.0),
    (-1.0, -1, 1.0),
    (3.0, 1, 0.28),
    (-3.0, -1, 0.28),
)

INSTRUMENT_RE = re.compile(
    r"^(?P<product>.+)-(?P<year>\d{4})-(?P<month>\d{2})"
    r"(?:-(?P<cp>[CP])-(?P<strike>\d+\.\d{2}))?$"
)


def _decimal(value: Decimal | float | int | str) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def q2(value: Decimal | float | int | str) -> Decimal:
    rounded = _decimal(value).quantize(CENT, rounding=ROUND_HALF_EVEN)
    return Decimal("0.00") if rounded == 0 else rounded


def scenario_money(value: float) -> Decimal:
    """Apply the methodology's explicit binary64 -> 10dp -> cent rule."""

    return q2(Decimal(format(float(value), ".10f")))


def _month_index(bucket: str) -> int:
    year, month = map(int, bucket.split("-"))
    return year * 12 + month - 1


def _month_date(bucket: str) -> date:
    year, month = map(int, bucket.split("-"))
    return date(year, month, 1)


@dataclass
class Position:
    iid: str
    qty: float
    product_name: str
    product: dict[str, Any]
    cc_id: str
    bucket: str
    forward: float
    effective_psr: float
    is_option: bool
    is_call: bool = False
    strike: float = 0.0
    vol: float = 0.0
    time: float = 0.0
    base_value: float = 0.0
    atm_delta: float = 1.0


def net_positions(portfolio: dict) -> dict[str, Decimal]:
    quantities: dict[str, Decimal] = defaultdict(Decimal)
    for row in portfolio["positions"]:
        quantities[row["instrument_id"]] += _decimal(row["qty"])
    return {iid: qty for iid, qty in quantities.items() if qty != 0}


def _parse_instrument(iid: str) -> tuple[str, int, int, str | None, float]:
    match = INSTRUMENT_RE.fullmatch(iid)
    if match is None:
        raise ValueError(f"invalid instrument_id: {iid}")
    year = int(match.group("year"))
    month = int(match.group("month"))
    if not 1 <= month <= 12:
        raise ValueError(f"invalid instrument month: {iid}")
    cp = match.group("cp")
    strike = float(match.group("strike")) if cp is not None else 0.0
    return match.group("product"), year, month, cp, strike


def _shock_forward(position: Position, price_multiplier: float) -> float:
    forward = position.forward
    shift = price_multiplier * position.effective_psr
    if position.product["shock_mode"] == "log":
        shocked = forward * math.exp(shift / forward) if forward > 0.0 else 1e-8
    else:
        shocked = forward + shift
    return max(shocked, 1e-8)


def _make_positions(
    portfolio: dict, market: dict, config: dict
) -> tuple[list[Position], dict[str, list[Position]]]:
    valuation_date = date.fromisoformat(market["valuation_date"])
    house = config["house"]
    result: list[Position] = []
    by_cc: dict[str, list[Position]] = defaultdict(list)

    for iid, net_qty in net_positions(portfolio).items():
        product_name, year, month, cp, strike = _parse_instrument(iid)
        product = config["products"][product_name]
        bucket = f"{year:04d}-{month:02d}"
        underlying = f"{product_name}-{bucket}"
        forward = float(market["futures_price"][underlying])
        delivery_days = (date(year, month, 1) - valuation_date).days
        if delivery_days <= int(house["delivery_scale_days"]):
            scale = 1.0
        else:
            scale = max(
                math.sqrt(delivery_days / 365.0),
                float(house["delivery_scale_floor"]),
            )
        effective_psr = float(product["price_scan_range"]) * scale

        position = Position(
            iid=iid,
            qty=float(net_qty),
            product_name=product_name,
            product=product,
            cc_id=product["cc_id"],
            bucket=bucket,
            forward=forward,
            effective_psr=effective_psr,
            is_option=cp is not None,
        )
        if cp is not None:
            expiry = date.fromisoformat(market["option_expiry"][iid])
            position.is_call = cp == "C"
            position.strike = strike
            position.vol = float(market["atm_vol"][iid])
            position.time = year_fraction(valuation_date, expiry)
            position.base_value = black_price(
                forward, strike, position.vol, position.time, position.is_call
            )
            position.atm_delta = black_delta(
                forward, strike, position.vol, position.time, position.is_call
            )
        result.append(position)
        by_cc[position.cc_id].append(position)
    return result, by_cc


def _scan_cc(
    positions: list[Position],
) -> tuple[dict[int, Decimal], dict[str, dict[int, float]]]:
    cc_pl = {scenario_id: Decimal("0.00") for scenario_id in range(1, 17)}
    deltas: dict[str, dict[int, float]] = {position.iid: {} for position in positions}

    for position in positions:
        multiplier = float(position.product["multiplier"])
        for scenario_id, (price_mult, vol_direction, weight) in enumerate(
            SCENARIOS, start=1
        ):
            shocked_forward = _shock_forward(position, price_mult)
            if position.is_option:
                fraction = (
                    float(position.product["vol_scan_fraction"])
                    if vol_direction > 0
                    else float(position.product["vsf_down"])
                )
                shocked_vol = max(
                    position.vol * (1.0 + vol_direction * fraction), 1e-6
                )
                shocked_value = black_price(
                    shocked_forward,
                    position.strike,
                    shocked_vol,
                    position.time,
                    position.is_call,
                )
                raw_pl = (
                    position.qty
                    * (shocked_value - position.base_value)
                    * multiplier
                    * weight
                )
                deltas[position.iid][scenario_id] = black_delta(
                    shocked_forward,
                    position.strike,
                    shocked_vol,
                    position.time,
                    position.is_call,
                )
            else:
                raw_pl = (
                    position.qty
                    * (shocked_forward - position.forward)
                    * multiplier
                    * weight
                )
                deltas[position.iid][scenario_id] = 1.0
            cc_pl[scenario_id] += scenario_money(raw_pl)
    return cc_pl, deltas


def _composite_buckets(
    positions: list[Position],
    cc_pl: dict[int, Decimal],
    deltas: dict[str, dict[int, float]],
    worst_scenario: int,
) -> dict[str, float]:
    if worst_scenario <= 14:
        next_scenario = min(
            (scenario_id for scenario_id in range(1, 15) if scenario_id != worst_scenario),
            key=lambda scenario_id: (cc_pl[scenario_id], scenario_id),
        )
    else:
        next_scenario = None

    contributions: dict[str, list[float]] = defaultdict(list)
    for position in positions:
        composite = deltas[position.iid][worst_scenario]
        if next_scenario is not None:
            composite = (composite + deltas[position.iid][next_scenario]) / 2.0
        contributions[position.bucket].append(position.qty * composite)
    return {
        bucket: math.fsum(bucket_contributions)
        for bucket, bucket_contributions in contributions.items()
    }


def _intra_spread(
    buckets: dict[str, float], product: dict[str, Any]
) -> tuple[Decimal, dict[str, float]]:
    remaining = dict(buckets)
    charges: list[Decimal] = []

    while True:
        nonzero = [bucket for bucket, value in remaining.items() if value != 0.0]
        if not any(remaining[bucket] > 0.0 for bucket in nonzero) or not any(
            remaining[bucket] < 0.0 for bucket in nonzero
        ):
            break
        bucket_a = min(nonzero, key=lambda bucket: (-abs(remaining[bucket]), bucket))
        sign_a = 1.0 if remaining[bucket_a] > 0.0 else -1.0
        opposite = [
            bucket
            for bucket in nonzero
            if (remaining[bucket] > 0.0) != (sign_a > 0.0)
        ]
        date_a = _month_date(bucket_a)
        bucket_b = min(
            opposite,
            key=lambda bucket: (
                abs((_month_date(bucket) - date_a).days),
                -abs(remaining[bucket]),
                bucket,
            ),
        )
        matched = min(abs(remaining[bucket_a]), abs(remaining[bucket_b]))
        days = abs((_month_date(bucket_b) - date_a).days)
        if days <= 32:
            rate = float(product["intra_tiers"]["adjacent"])
        elif days <= 125:
            rate = float(product["intra_tiers"]["mid"])
        else:
            rate = float(product["intra_tiers"]["back"])
        charges.append(
            _decimal(matched)
            * _decimal(rate)
            * _decimal(math.sqrt(days / 365.0))
        )

        for bucket in (bucket_a, bucket_b):
            old = remaining[bucket]
            if abs(old) <= matched:
                remaining[bucket] = 0.0
            else:
                remaining[bucket] = old - math.copysign(matched, old)

    return q2(sum(charges, Decimal(0))), remaining


def _strip_credit(remaining: dict[str, float], strip_rate: float) -> Decimal:
    # Zeroed buckets remain part of the post-matching month sequence. If one
    # lies in a run, the prescribed minimum residual makes that run's credit 0.
    months = sorted(remaining)
    if strip_rate == 0.0 or len(months) < 3:
        return Decimal("0.00")

    runs: list[list[str]] = []
    current: list[str] = []
    for bucket in months:
        if not current or _month_index(bucket) == _month_index(current[-1]) + 1:
            current.append(bucket)
        else:
            runs.append(current)
            current = [bucket]
    if current:
        runs.append(current)

    credits: list[Decimal] = []
    for run in runs:
        if len(run) >= 3:
            minimum = min(abs(remaining[bucket]) for bucket in run)
            credits.append(
                _decimal(len(run) - 2) * _decimal(strip_rate) * _decimal(minimum)
            )
    return q2(sum(credits, Decimal(0)))


def _cc_catalog(products: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
    for product_name in sorted(products):
        product = products[product_name]
        catalog.setdefault(product["cc_id"], product)
    return catalog


def _apply_inter_spreads(
    outright: dict[str, float],
    config: dict,
    catalog: dict[str, dict[str, Any]],
) -> tuple[dict[str, Decimal], dict[str, float]]:
    residual = dict(outright)
    credits = {cc_id: Decimal("0.00") for cc_id in outright}

    for spread in sorted(config["inter_spreads"], key=lambda item: item["priority"]):
        leg_a, leg_b = spread["leg_a"], spread["leg_b"]
        if leg_a not in catalog or leg_b not in catalog:
            continue
        product_a, product_b = catalog[leg_a], catalog[leg_b]
        if (
            product_a["ics_group"] != product_b["ics_group"]
            or product_a["currency"] != product_b["currency"]
            or spread["ics_group"] != product_a["ics_group"]
        ):
            continue
        delta_a = residual.get(leg_a, 0.0)
        delta_b = residual.get(leg_b, 0.0)
        ratio_a = float(spread["ratio_a"])
        ratio_b = float(spread["ratio_b"])
        if delta_a == 0.0 or delta_b == 0.0 or ratio_a <= 0.0 or ratio_b <= 0.0:
            continue
        units_a, units_b = delta_a / ratio_a, delta_b / ratio_b
        if (units_a > 0.0) == (units_b > 0.0):
            continue

        paired = min(abs(units_a), abs(units_b))
        credit = q2(
            _decimal(paired)
            * _decimal(spread["credit_per_unit"])
            * (Decimal(1) - _decimal(spread["rho"]))
        )
        credit_b = q2(credit / 2)
        credit_a = credit - credit_b
        if leg_a in credits:
            credits[leg_a] += credit_a
        if leg_b in credits:
            credits[leg_b] += credit_b

        residual[leg_a] = (
            0.0
            if abs(units_a) <= paired
            else delta_a - math.copysign(paired * ratio_a, delta_a)
        )
        residual[leg_b] = (
            0.0
            if abs(units_b) <= paired
            else delta_b - math.copysign(paired * ratio_b, delta_b)
        )
    return credits, residual


def _option_adjustments(
    positions: list[Position], scanning_risk: Decimal
) -> tuple[Decimal, Decimal, Decimal]:
    som_parts: list[Decimal] = []
    nov_parts: list[Decimal] = []
    liquidity_parts: list[Decimal] = []

    for position in positions:
        if not position.is_option:
            continue
        absolute_delta = abs(position.atm_delta)
        if position.qty < 0.0:
            som_parts.append(
                _decimal(position.product["som_rate"])
                * _decimal(abs(position.qty))
                * (Decimal(1) + _decimal(max(0.0, 0.25 - absolute_delta)))
            )
            liquidity_parts.append(
                _decimal(position.product["lao_rate"])
                * _decimal(abs(position.qty))
                * _decimal(
                    max(0.0, float(position.product["lao_otm"]) - absolute_delta)
                )
            )
        elif position.qty > 0.0 and absolute_delta < 0.35:
            nov_parts.append(
                max(
                    Decimal(0),
                    _decimal(position.qty)
                    * _decimal(position.base_value)
                    * _decimal(position.product["multiplier"]),
                )
            )

    som = q2(sum(som_parts, Decimal(0)))
    uncapped_nov = sum(nov_parts, Decimal(0))
    nov = q2(min(uncapped_nov, scanning_risk))
    liquidity = q2(sum(liquidity_parts, Decimal(0)))
    return som, nov, liquidity


def compute_report(portfolio: dict, market: dict, config: dict) -> dict:
    _positions, by_cc = _make_positions(portfolio, market, config)
    products = config["products"]
    catalog = _cc_catalog(products)
    fx = {currency: _decimal(value) for currency, value in market["fx_to_usd"].items()}

    intermediate: dict[str, dict[str, Any]] = {}
    outright: dict[str, float] = {}
    for cc_id, positions in by_cc.items():
        cc_pl, deltas = _scan_cc(positions)
        worst_scenario = min(range(1, 17), key=lambda sid: (cc_pl[sid], sid))
        scanning_risk = q2(max(Decimal(0), -cc_pl[worst_scenario]))
        buckets = _composite_buckets(positions, cc_pl, deltas, worst_scenario)
        product = catalog[cc_id]
        intra_charge, remaining = _intra_spread(buckets, product)
        strip_credit = _strip_credit(remaining, float(product["strip_rate"]))
        outright[cc_id] = math.fsum(remaining.values())
        intermediate[cc_id] = {
            "positions": positions,
            "scanning_risk": scanning_risk,
            "worst_scenario": worst_scenario,
            "intra_charge": intra_charge,
            "strip_credit": strip_credit,
        }

    inter_credits, residual = _apply_inter_spreads(outright, config, catalog)

    rows: list[dict[str, Any]] = []
    total = Decimal("0.00")
    for cc_id in sorted(by_cc):
        state = intermediate[cc_id]
        product = catalog[cc_id]
        scanning_risk = state["scanning_risk"]
        som, nov_credit, liquidity_addon = _option_adjustments(
            state["positions"], scanning_risk
        )
        excess = max(
            0.0,
            abs(residual.get(cc_id, 0.0))
            - float(product["concentration_threshold"]),
        )
        concentration_charge = q2(
            _decimal(excess) * _decimal(product["concentration_rate"])
        )
        inter_credit = q2(inter_credits.get(cc_id, Decimal("0.00")))
        raw_margin = q2(
            scanning_risk
            + state["intra_charge"]
            + concentration_charge
            - inter_credit
            - nov_credit
            - state["strip_credit"]
        )
        margin_native = max(raw_margin, som) + liquidity_addon
        currency = product["currency"]
        margin_usd = q2(margin_native * fx[currency])
        total += margin_usd
        rows.append(
            {
                "cc_id": cc_id,
                "currency": currency,
                "scanning_risk": scanning_risk,
                "intra_charge": state["intra_charge"],
                "inter_credit": inter_credit,
                "nov_credit": nov_credit,
                "som": som,
                "strip_credit": state["strip_credit"],
                "concentration_charge": concentration_charge,
                "liquidity_addon": liquidity_addon,
                "raw_margin": raw_margin,
                "cc_margin_native": margin_native,
                "cc_margin_usd": margin_usd,
                "worst_scenario_id": int(state["worst_scenario"]),
            }
        )

    return {
        "valuation_date": market["valuation_date"],
        "currency": "USD",
        "total_margin_usd": q2(total),
        "combined_commodities": rows,
    }


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def _json_text(value: Any, level: int = 0) -> str:
    """Pretty-print JSON while preserving two decimal places on money."""

    indent = "  " * level
    child_indent = "  " * (level + 1)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("non-finite money value")
        return format(q2(value), ".2f")
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = [
            f"{child_indent}{json.dumps(str(key))}: {_json_text(item, level + 1)}"
            for key, item in value.items()
        ]
        return "{\n" + ",\n".join(items) + f"\n{indent}}}"
    if isinstance(value, list):
        if not value:
            return "[]"
        items = [f"{child_indent}{_json_text(item, level + 1)}" for item in value]
        return "[\n" + ",\n".join(items) + f"\n{indent}]"
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def write_report(report: dict, path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_json_text(report) + "\n")
