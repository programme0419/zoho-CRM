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

try:  # Support both ``python hsm/run_margin.py`` and package imports.
    from .lib.black76 import delta as black_delta
    from .lib.black76 import price as black_price
    from .lib.black76 import year_fraction
except ImportError:  # pragma: no cover - this is the required CLI path
    from lib.black76 import delta as black_delta
    from lib.black76 import price as black_price
    from lib.black76 import year_fraction


CENT = Decimal("0.01")

# (scenario id, price multiplier, vol direction, P/L weight).  vol direction
# selects the asymmetric up/down fraction configured for the product.
SCENARIOS = (
    (1, 0.0, 1, 1.0),
    (2, 0.0, -1, 1.0),
    (3, 1.0 / 3.0, 1, 1.0),
    (4, 1.0 / 3.0, -1, 1.0),
    (5, -1.0 / 3.0, 1, 1.0),
    (6, -1.0 / 3.0, -1, 1.0),
    (7, 2.0 / 3.0, 1, 1.0),
    (8, 2.0 / 3.0, -1, 1.0),
    (9, -2.0 / 3.0, 1, 1.0),
    (10, -2.0 / 3.0, -1, 1.0),
    (11, 1.0, 1, 1.0),
    (12, 1.0, -1, 1.0),
    (13, -1.0, 1, 1.0),
    (14, -1.0, -1, 1.0),
    (15, 3.0, 1, 0.28),
    (16, -3.0, -1, 0.28),
)

MONEY_FIELDS = {
    "total_margin_usd",
    "scanning_risk",
    "intra_charge",
    "inter_credit",
    "nov_credit",
    "som",
    "strip_credit",
    "concentration_charge",
    "liquidity_addon",
    "raw_margin",
    "cc_margin_native",
    "cc_margin_usd",
}


def _decimal(value: Decimal | float | int | str) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def q2(value: Decimal | float | int | str) -> Decimal:
    result = _decimal(value).quantize(CENT, rounding=ROUND_HALF_EVEN)
    return Decimal("0.00") if result == 0 else result


def money(value: float) -> Decimal:
    """Apply the methodology's special scenario P/L conversion rule."""

    result = Decimal(format(float(value), ".10f")).quantize(CENT, rounding=ROUND_HALF_EVEN)
    return Decimal("0.00") if result == 0 else result


def net_positions(portfolio: dict) -> dict[str, float]:
    """Net duplicate rows exactly as decimal contract quantities."""

    quantities: defaultdict[str, Decimal] = defaultdict(Decimal)
    for row in portfolio["positions"]:
        quantities[row["instrument_id"]] += _decimal(row["qty"])
    return {
        instrument_id: float(qty)
        for instrument_id, qty in sorted(quantities.items())
        if qty != 0
    }


@dataclass
class Position:
    instrument_id: str
    product: str
    bucket: str
    qty: float
    option: bool
    atm_delta: float
    base_value: float
    scenario_pl: list[Decimal]
    scenario_delta: list[float]


def _parse_instrument(instrument_id: str) -> tuple[str, str, bool, bool, float]:
    parts = instrument_id.split("-")
    if len(parts) == 3:
        product, year, month = parts
        return product, f"{year}-{month}", False, False, 0.0
    if len(parts) == 5 and parts[3] in ("C", "P"):
        product, year, month, cp, strike = parts
        return product, f"{year}-{month}", True, cp == "C", float(strike)
    raise ValueError(f"invalid instrument_id: {instrument_id}")


def _delivery_psr(
    product: dict, bucket: str, valuation_date: date, house: dict
) -> float:
    year, month = (int(part) for part in bucket.split("-"))
    delivery_days = (date(year, month, 1) - valuation_date).days
    if delivery_days <= int(house["delivery_scale_days"]):
        scale = 1.0
    else:
        scale = max(
            math.sqrt(delivery_days / 365.0),
            float(house["delivery_scale_floor"]),
        )
    return float(product["price_scan_range"]) * scale


def _shocked_forward(forward: float, price_mult: float, psr: float, mode: str) -> float:
    if mode == "linear":
        return max(forward + price_mult * psr, 1.0e-8)
    if mode == "log":
        if forward <= 0.0:
            return 1.0e-8
        return max(forward * math.exp(price_mult * psr / forward), 1.0e-8)
    raise ValueError(f"invalid shock_mode: {mode}")


def _prepare_position(
    instrument_id: str,
    qty: float,
    market: dict,
    products: dict,
    valuation_date: date,
    house: dict,
) -> Position:
    product_name, bucket, option, is_call, strike = _parse_instrument(instrument_id)
    product = products[product_name]
    future_id = f"{product_name}-{bucket}"
    forward = float(market["futures_price"][future_id])
    multiplier = float(product["multiplier"])
    psr = _delivery_psr(product, bucket, valuation_date, house)

    if option:
        vol = float(market["atm_vol"][instrument_id])
        expiry = date.fromisoformat(market["option_expiry"][instrument_id])
        t = year_fraction(valuation_date, expiry)
        base_value = black_price(forward, strike, vol, t, is_call)
        atm_delta = black_delta(forward, strike, vol, t, is_call)
    else:
        vol = 0.0
        t = 0.0
        base_value = 0.0
        atm_delta = 1.0

    scenario_pl: list[Decimal] = []
    scenario_delta: list[float] = []
    for _sid, price_mult, vol_direction, weight in SCENARIOS:
        shocked_forward = _shocked_forward(
            forward, price_mult, psr, product["shock_mode"]
        )
        if option:
            fraction = (
                float(product["vol_scan_fraction"])
                if vol_direction > 0
                else float(product["vsf_down"])
            )
            signed_fraction = fraction if vol_direction > 0 else -fraction
            shocked_vol = max(vol * (1.0 + signed_fraction), 1.0e-6)
            shocked_value = black_price(
                shocked_forward, strike, shocked_vol, t, is_call
            )
            pl = qty * (shocked_value - base_value) * multiplier * weight
            unit_delta = black_delta(
                shocked_forward, strike, shocked_vol, t, is_call
            )
        else:
            pl = qty * (shocked_forward - forward) * multiplier * weight
            unit_delta = 1.0
        scenario_pl.append(money(pl))
        scenario_delta.append(unit_delta)

    return Position(
        instrument_id=instrument_id,
        product=product_name,
        bucket=bucket,
        qty=qty,
        option=option,
        atm_delta=atm_delta,
        base_value=base_value,
        scenario_pl=scenario_pl,
        scenario_delta=scenario_delta,
    )


def _month_date(bucket: str) -> date:
    year, month = (int(part) for part in bucket.split("-"))
    return date(year, month, 1)


def _month_ordinal(bucket: str) -> int:
    year, month = (int(part) for part in bucket.split("-"))
    return year * 12 + month - 1


def _intra_match(
    bucket_deltas: dict[str, float], tiers: dict
) -> tuple[Decimal, dict[str, float]]:
    remaining = dict(bucket_deltas)
    charges: list[float] = []

    while True:
        nonzero = [bucket for bucket, value in remaining.items() if value != 0.0]
        has_positive = any(remaining[bucket] > 0.0 for bucket in nonzero)
        has_negative = any(remaining[bucket] < 0.0 for bucket in nonzero)
        if not (has_positive and has_negative):
            break

        bucket_a = min(nonzero, key=lambda bucket: (-abs(remaining[bucket]), bucket))
        value_a = remaining[bucket_a]
        opposites = [
            bucket
            for bucket in nonzero
            if (remaining[bucket] < 0.0) != (value_a < 0.0)
        ]
        date_a = _month_date(bucket_a)
        bucket_b = min(
            opposites,
            key=lambda bucket: (
                abs((_month_date(bucket) - date_a).days),
                -abs(remaining[bucket]),
                bucket,
            ),
        )
        value_b = remaining[bucket_b]
        matched = min(abs(value_a), abs(value_b))
        distance = abs((_month_date(bucket_b) - date_a).days)
        if distance <= 32:
            rate = float(tiers["adjacent"])
        elif distance <= 125:
            rate = float(tiers["mid"])
        else:
            rate = float(tiers["back"])
        charges.append(matched * rate * math.sqrt(distance / 365.0))

        new_a = abs(value_a) - matched
        new_b = abs(value_b) - matched
        remaining[bucket_a] = math.copysign(new_a, value_a) if new_a > 0.0 else 0.0
        remaining[bucket_b] = math.copysign(new_b, value_b) if new_b > 0.0 else 0.0

    return q2(math.fsum(charges)), remaining


def _strip_credit(remaining: dict[str, float], strip_rate: float) -> Decimal:
    if strip_rate == 0.0:
        return Decimal("0.00")
    months = sorted(
        (bucket for bucket, value in remaining.items() if value != 0.0),
        key=_month_ordinal,
    )
    if len(months) < 3:
        return Decimal("0.00")

    runs: list[list[str]] = []
    run = [months[0]]
    for bucket in months[1:]:
        if _month_ordinal(bucket) == _month_ordinal(run[-1]) + 1:
            run.append(bucket)
        else:
            runs.append(run)
            run = [bucket]
    runs.append(run)

    credits = [
        (len(item) - 2)
        * strip_rate
        * min(abs(remaining[bucket]) for bucket in item)
        for item in runs
        if len(item) >= 3
    ]
    return q2(math.fsum(credits))


def _option_amounts(
    positions: list[Position], products: dict
) -> tuple[Decimal, float, Decimal]:
    som_parts: list[float] = []
    nov_parts: list[float] = []
    liquidity_parts: list[float] = []
    for position in positions:
        if not position.option:
            continue
        product = products[position.product]
        absolute_delta = abs(position.atm_delta)
        if position.qty < 0.0:
            som_parts.append(
                float(product["som_rate"])
                * abs(position.qty)
                * (1.0 + max(0.0, 0.25 - absolute_delta))
            )
            liquidity_parts.append(
                float(product["lao_rate"])
                * abs(position.qty)
                * max(0.0, float(product["lao_otm"]) - absolute_delta)
            )
        elif position.qty > 0.0 and absolute_delta < 0.35:
            nov_parts.append(
                max(
                    0.0,
                    position.qty
                    * position.base_value
                    * float(product["multiplier"]),
                )
            )
    return q2(math.fsum(som_parts)), math.fsum(nov_parts), q2(math.fsum(liquidity_parts))


def _shared_cc_attributes(config_products: dict) -> dict[str, dict[str, str | None]]:
    values: defaultdict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"currency": set(), "ics_group": set()}
    )
    for product in config_products.values():
        cc_id = product["cc_id"]
        values[cc_id]["currency"].add(product["currency"])
        values[cc_id]["ics_group"].add(product["ics_group"])
    result: dict[str, dict[str, str | None]] = {}
    for cc_id, attrs in values.items():
        result[cc_id] = {
            name: next(iter(items)) if len(items) == 1 else None
            for name, items in attrs.items()
        }
    return result


def _apply_inter_spreads(states: dict[str, dict], config: dict) -> None:
    cc_attrs = _shared_cc_attributes(config["products"])
    for spread in sorted(config["inter_spreads"], key=lambda item: item["priority"]):
        cc_a = spread["leg_a"]
        cc_b = spread["leg_b"]
        if cc_a not in states or cc_b not in states:
            continue

        attrs_a = cc_attrs.get(cc_a, {})
        attrs_b = cc_attrs.get(cc_b, {})
        currency_a = attrs_a.get("currency")
        currency_b = attrs_b.get("currency")
        group_a = attrs_a.get("ics_group")
        group_b = attrs_b.get("ics_group")
        if (
            currency_a is None
            or currency_a != currency_b
            or group_a is None
            or group_a != group_b
            or group_a != spread["ics_group"]
        ):
            continue

        delta_a = states[cc_a]["residual"]
        delta_b = states[cc_b]["residual"]
        if delta_a == 0.0 or delta_b == 0.0 or (delta_a < 0.0) == (delta_b < 0.0):
            continue
        ratio_a = float(spread["ratio_a"])
        ratio_b = float(spread["ratio_b"])
        if ratio_a <= 0.0 or ratio_b <= 0.0:
            continue
        units_a = delta_a / ratio_a
        units_b = delta_b / ratio_b
        if (units_a < 0.0) == (units_b < 0.0):
            continue

        paired = min(abs(units_a), abs(units_b))
        credit = q2(
            paired
            * float(spread["credit_per_unit"])
            * (1.0 - float(spread["rho"]))
        )
        credit_b = q2(credit / 2)
        credit_a = credit - credit_b
        states[cc_a]["inter_credit"] += credit_a
        states[cc_b]["inter_credit"] += credit_b

        states[cc_a]["residual"] = (
            0.0
            if abs(units_a) <= paired
            else math.copysign((abs(units_a) - paired) * ratio_a, delta_a)
        )
        states[cc_b]["residual"] = (
            0.0
            if abs(units_b) <= paired
            else math.copysign((abs(units_b) - paired) * ratio_b, delta_b)
        )


def compute_report(portfolio: dict, market: dict, config: dict) -> dict:
    net = net_positions(portfolio)
    products = config["products"]
    valuation_date = date.fromisoformat(market["valuation_date"])
    prepared = [
        _prepare_position(
            instrument_id,
            qty,
            market,
            products,
            valuation_date,
            config["house"],
        )
        for instrument_id, qty in net.items()
    ]

    by_cc: defaultdict[str, list[Position]] = defaultdict(list)
    for position in prepared:
        by_cc[products[position.product]["cc_id"]].append(position)

    states: dict[str, dict] = {}
    for cc_id, positions in by_cc.items():
        positions.sort(key=lambda item: item.instrument_id)
        product_names = sorted({position.product for position in positions})
        representative = products[product_names[0]]
        currencies = {products[name]["currency"] for name in product_names}
        if len(currencies) != 1:
            raise ValueError(f"combined commodity {cc_id} contains multiple currencies")

        cc_pl = [
            sum((position.scenario_pl[index] for position in positions), Decimal("0.00"))
            for index in range(16)
        ]
        worst_index = min(range(16), key=lambda index: (cc_pl[index], index + 1))
        worst_scenario_id = worst_index + 1
        scanning_risk = q2(max(Decimal(0), -cc_pl[worst_index]))

        if worst_scenario_id <= 14:
            second_index = min(
                (index for index in range(14) if index != worst_index),
                key=lambda index: (cc_pl[index], index + 1),
            )
        else:
            second_index = None

        bucket_parts: defaultdict[str, list[float]] = defaultdict(list)
        for position in positions:
            if second_index is None:
                composite_unit = position.scenario_delta[worst_index]
            else:
                composite_unit = (
                    position.scenario_delta[worst_index]
                    + position.scenario_delta[second_index]
                ) / 2.0
            bucket_parts[position.bucket].append(composite_unit * position.qty)
        bucket_deltas = {
            bucket: math.fsum(parts) for bucket, parts in bucket_parts.items()
        }

        intra_charge, remaining = _intra_match(
            bucket_deltas, representative["intra_tiers"]
        )
        strip_credit = _strip_credit(
            remaining, float(representative["strip_rate"])
        )
        som, nov_unrounded, liquidity_addon = _option_amounts(positions, products)
        states[cc_id] = {
            "positions": positions,
            "product": representative,
            "currency": next(iter(currencies)),
            "scanning_risk": scanning_risk,
            "worst_scenario_id": worst_scenario_id,
            "intra_charge": intra_charge,
            "remaining": remaining,
            "strip_credit": strip_credit,
            "som": som,
            "nov_unrounded": nov_unrounded,
            "liquidity_addon": liquidity_addon,
            "inter_credit": Decimal("0.00"),
            "residual": math.fsum(remaining.values()),
        }

    _apply_inter_spreads(states, config)

    rows: list[dict] = []
    total = Decimal("0.00")
    for cc_id in sorted(states):
        state = states[cc_id]
        product = state["product"]
        threshold = float(product["concentration_threshold"])
        excess = max(0.0, abs(state["residual"]) - threshold)
        concentration_charge = q2(excess * float(product["concentration_rate"]))
        nov_credit = q2(
            min(state["nov_unrounded"], float(state["scanning_risk"]))
        )
        raw_margin = q2(
            state["scanning_risk"]
            + state["intra_charge"]
            + concentration_charge
            - state["inter_credit"]
            - nov_credit
            - state["strip_credit"]
        )
        native_before_liquidity = max(raw_margin, state["som"])
        cc_margin_native = native_before_liquidity + state["liquidity_addon"]
        fx = _decimal(market["fx_to_usd"][state["currency"]])
        cc_margin_usd = q2(cc_margin_native * fx)
        total += cc_margin_usd

        rows.append(
            {
                "cc_id": cc_id,
                "currency": state["currency"],
                "scanning_risk": float(state["scanning_risk"]),
                "intra_charge": float(state["intra_charge"]),
                "inter_credit": float(state["inter_credit"]),
                "nov_credit": float(nov_credit),
                "som": float(state["som"]),
                "strip_credit": float(state["strip_credit"]),
                "concentration_charge": float(concentration_charge),
                "liquidity_addon": float(state["liquidity_addon"]),
                "raw_margin": float(raw_margin),
                "cc_margin_native": float(cc_margin_native),
                "cc_margin_usd": float(cc_margin_usd),
                "worst_scenario_id": state["worst_scenario_id"],
            }
        )

    return {
        "valuation_date": market["valuation_date"],
        "currency": "USD",
        "total_margin_usd": float(total),
        "combined_commodities": rows,
    }


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def _with_money_tokens(value: Any, key: str | None = None) -> Any:
    if key in MONEY_FIELDS:
        return f"__HSM_MONEY__{q2(value):.2f}__"
    if isinstance(value, dict):
        return {
            child_key: _with_money_tokens(child, child_key)
            for child_key, child in value.items()
        }
    if isinstance(value, list):
        return [_with_money_tokens(child) for child in value]
    return value


def write_report(report: dict, path: str | Path) -> None:
    """Write report JSON while preserving the required two money decimals."""

    rendered = json.dumps(_with_money_tokens(report), indent=2)
    rendered = re.sub(r'"__HSM_MONEY__(-?[0-9]+\.[0-9]{2})__"', r"\1", rendered)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered + "\n")
