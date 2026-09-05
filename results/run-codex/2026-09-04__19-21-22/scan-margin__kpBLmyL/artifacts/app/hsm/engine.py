"""House Scan Margin calculation, including all house overlays."""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Any

try:  # Supports both the CLI's top-level import and package-style test imports.
    from .lib.black76 import delta as black_delta
    from .lib.black76 import price as black_price
    from .lib.black76 import year_fraction
except ImportError:  # pragma: no cover - this is the run_margin.py import path
    from lib.black76 import delta as black_delta
    from lib.black76 import price as black_price
    from lib.black76 import year_fraction


CENT = Decimal("0.01")
ZERO = Decimal("0.00")

# (price multiplier, volatility direction, P/L weight), in scenario-id order.
SCENARIOS = (
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

_FUTURE_RE = re.compile(r"^([^-]+)-(\d{4})-(\d{2})$")
_OPTION_RE = re.compile(
    r"^([^-]+)-(\d{4})-(\d{2})-([CP])-(-?(?:\d+(?:\.\d*)?|\.\d+))$"
)


def _decimal(value: Decimal | int | float | str) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def q2(value: Decimal | int | float | str) -> Decimal:
    rounded = _decimal(value).quantize(CENT, rounding=ROUND_HALF_EVEN)
    return ZERO if rounded == 0 else rounded


def money(value: float) -> Decimal:
    """Apply the special per-position/scenario binary64 conversion rule."""

    rounded = Decimal(format(float(value), ".10f")).quantize(
        CENT, rounding=ROUND_HALF_EVEN
    )
    return ZERO if rounded == 0 else rounded


def net_positions(portfolio: dict) -> dict[str, float]:
    quantities: defaultdict[str, Decimal] = defaultdict(Decimal)
    for row in portfolio["positions"]:
        quantities[row["instrument_id"]] += _decimal(row["qty"])
    return {
        instrument_id: float(qty)
        for instrument_id, qty in quantities.items()
        if qty != 0
    }


@dataclass
class Position:
    instrument_id: str
    qty: float
    product: str
    year: int
    month: int
    product_config: dict
    forward: float
    effective_psr: float
    is_option: bool = False
    is_call: bool = False
    strike: float = 0.0
    vol: float = 0.0
    t: float = 0.0
    base_value: float = 0.0
    atm_delta: float = 1.0
    scenario_deltas: list[float] = field(default_factory=list)

    @property
    def bucket(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


def _parse_instrument(instrument_id: str) -> tuple[str, int, int, str | None, float]:
    option_match = _OPTION_RE.fullmatch(instrument_id)
    if option_match:
        product, year, month, cp, strike = option_match.groups()
        parsed_month = int(month)
        date(int(year), parsed_month, 1)  # validates the calendar month
        return product, int(year), parsed_month, cp, float(strike)

    future_match = _FUTURE_RE.fullmatch(instrument_id)
    if future_match:
        product, year, month = future_match.groups()
        parsed_month = int(month)
        date(int(year), parsed_month, 1)
        return product, int(year), parsed_month, None, 0.0
    raise ValueError(f"invalid instrument_id: {instrument_id}")


def _build_position(
    instrument_id: str,
    qty: float,
    market: dict,
    config: dict,
    valuation_date: date,
) -> Position:
    product, year, month, cp, strike = _parse_instrument(instrument_id)
    product_config = config["products"][product]
    underlying = f"{product}-{year:04d}-{month:02d}"
    forward = float(market["futures_price"][underlying])

    delivery_days = (date(year, month, 1) - valuation_date).days
    if delivery_days <= int(config["house"]["delivery_scale_days"]):
        delivery_scale = 1.0
    else:
        delivery_scale = max(
            math.sqrt(delivery_days / 365.0),
            float(config["house"]["delivery_scale_floor"]),
        )
    effective_psr = float(product_config["price_scan_range"]) * delivery_scale

    position = Position(
        instrument_id=instrument_id,
        qty=qty,
        product=product,
        year=year,
        month=month,
        product_config=product_config,
        forward=forward,
        effective_psr=effective_psr,
    )
    if cp is not None:
        valuation_expiry = date.fromisoformat(market["option_expiry"][instrument_id])
        vol = float(market["atm_vol"][instrument_id])
        t = year_fraction(valuation_date, valuation_expiry)
        is_call = cp == "C"
        position.is_option = True
        position.is_call = is_call
        position.strike = strike
        position.vol = vol
        position.t = t
        position.base_value = black_price(forward, strike, vol, t, is_call)
        position.atm_delta = black_delta(forward, strike, vol, t, is_call)
    return position


def _shocked_forward(position: Position, price_multiplier: float) -> float:
    if position.product_config["shock_mode"] == "linear":
        shocked = position.forward + price_multiplier * position.effective_psr
    elif position.forward > 0.0:
        shocked = position.forward * math.exp(
            price_multiplier * position.effective_psr / position.forward
        )
    else:
        shocked = 1e-8
    return max(shocked, 1e-8)


def _scenario_values(position: Position, scenario_index: int) -> tuple[float, float]:
    price_multiplier, vol_direction, weight = SCENARIOS[scenario_index]
    shocked_forward = _shocked_forward(position, price_multiplier)
    multiplier = float(position.product_config["multiplier"])

    if not position.is_option:
        pnl = (
            position.qty
            * (shocked_forward - position.forward)
            * multiplier
            * weight
        )
        return pnl, 1.0

    if vol_direction > 0:
        vol_fraction = float(position.product_config["vol_scan_fraction"])
    else:
        vol_fraction = -float(position.product_config["vsf_down"])
    shocked_vol = max(position.vol * (1.0 + vol_fraction), 1e-6)
    shocked_value = black_price(
        shocked_forward,
        position.strike,
        shocked_vol,
        position.t,
        position.is_call,
    )
    pnl = (
        position.qty
        * (shocked_value - position.base_value)
        * multiplier
        * weight
    )
    shocked_delta = black_delta(
        shocked_forward,
        position.strike,
        shocked_vol,
        position.t,
        position.is_call,
    )
    return pnl, shocked_delta


def _month_day_distance(left: str, right: str) -> int:
    left_year, left_month = (int(part) for part in left.split("-"))
    right_year, right_month = (int(part) for part in right.split("-"))
    return abs(
        (date(left_year, left_month, 1) - date(right_year, right_month, 1)).days
    )


def _toward_zero(value: float, amount: float) -> float:
    if amount >= abs(value):
        return 0.0
    return value - math.copysign(amount, value)


def _intra_spread(
    bucket_deltas: dict[str, float], tiers: dict
) -> tuple[Decimal, dict[str, float]]:
    remaining = dict(bucket_deltas)
    charges: list[float] = []

    while True:
        nonzero = [bucket for bucket, delta in remaining.items() if delta != 0.0]
        if not any(remaining[bucket] > 0.0 for bucket in nonzero) or not any(
            remaining[bucket] < 0.0 for bucket in nonzero
        ):
            break

        bucket_a = min(nonzero, key=lambda bucket: (-abs(remaining[bucket]), bucket))
        opposite = [
            bucket
            for bucket in nonzero
            if remaining[bucket] * remaining[bucket_a] < 0.0
        ]
        bucket_b = min(
            opposite,
            key=lambda bucket: (
                _month_day_distance(bucket_a, bucket),
                -abs(remaining[bucket]),
                bucket,
            ),
        )
        matched = min(abs(remaining[bucket_a]), abs(remaining[bucket_b]))
        remaining[bucket_a] = _toward_zero(remaining[bucket_a], matched)
        remaining[bucket_b] = _toward_zero(remaining[bucket_b], matched)

        distance = _month_day_distance(bucket_a, bucket_b)
        if distance <= 32:
            rate = float(tiers["adjacent"])
        elif distance <= 125:
            rate = float(tiers["mid"])
        else:
            rate = float(tiers["back"])
        charges.append(matched * rate * math.sqrt(distance / 365.0))

    return q2(math.fsum(charges)), remaining


def _month_ordinal(bucket: str) -> int:
    year, month = (int(part) for part in bucket.split("-"))
    return year * 12 + month


def _strip_credit(remaining: dict[str, float], strip_rate: float) -> Decimal:
    if strip_rate == 0.0:
        return ZERO
    months = sorted(bucket for bucket, delta in remaining.items() if delta != 0.0)
    if len(months) < 3:
        return ZERO

    runs: list[list[str]] = []
    run: list[str] = []
    for month in months:
        if run and _month_ordinal(month) != _month_ordinal(run[-1]) + 1:
            runs.append(run)
            run = []
        run.append(month)
    if run:
        runs.append(run)

    credits = [
        (len(candidate) - 2)
        * strip_rate
        * min(abs(remaining[month]) for month in candidate)
        for candidate in runs
        if len(candidate) >= 3
    ]
    return q2(math.fsum(credits))


def _short_option_minimum(positions: list[Position]) -> Decimal:
    contributions = [
        float(position.product_config["som_rate"])
        * abs(position.qty)
        * (1.0 + max(0.0, 0.25 - abs(position.atm_delta)))
        for position in positions
        if position.is_option and position.qty < 0.0
    ]
    return q2(math.fsum(contributions))


def _nov_credit(positions: list[Position], scanning_risk: Decimal) -> Decimal:
    contributions = [
        max(
            0.0,
            position.qty
            * position.base_value
            * float(position.product_config["multiplier"]),
        )
        for position in positions
        if position.is_option
        and position.qty > 0.0
        and abs(position.atm_delta) < 0.35
    ]
    uncapped = _decimal(math.fsum(contributions))
    return q2(min(uncapped, scanning_risk))


def _liquidity_addon(positions: list[Position]) -> Decimal:
    contributions = [
        float(position.product_config["lao_rate"])
        * abs(position.qty)
        * max(
            0.0,
            float(position.product_config["lao_otm"]) - abs(position.atm_delta),
        )
        for position in positions
        if position.is_option and position.qty < 0.0
    ]
    return q2(math.fsum(contributions))


def _representative_products(config: dict) -> dict[str, tuple[str, dict]]:
    result: dict[str, tuple[str, dict]] = {}
    for product in sorted(config["products"]):
        product_config = config["products"][product]
        result.setdefault(product_config["cc_id"], (product, product_config))
    return result


def _apply_inter_spreads(
    states: dict[str, dict], config: dict, cc_products: dict[str, tuple[str, dict]]
) -> None:
    residual = {cc_id: state["outright_delta"] for cc_id, state in states.items()}
    credits = {cc_id: ZERO for cc_id in states}

    for spread in sorted(config["inter_spreads"], key=lambda row: row["priority"]):
        leg_a = spread["leg_a"]
        leg_b = spread["leg_b"]
        if leg_a not in cc_products or leg_b not in cc_products:
            continue
        config_a = cc_products[leg_a][1]
        config_b = cc_products[leg_b][1]
        if not (
            config_a["ics_group"]
            == config_b["ics_group"]
            == spread["ics_group"]
            and config_a["currency"] == config_b["currency"]
        ):
            continue

        delta_a = residual.get(leg_a, 0.0)
        delta_b = residual.get(leg_b, 0.0)
        if delta_a == 0.0 or delta_b == 0.0:
            continue
        ratio_a = float(spread["ratio_a"])
        ratio_b = float(spread["ratio_b"])
        if ratio_a <= 0.0 or ratio_b <= 0.0:
            continue
        units_a = delta_a / ratio_a
        units_b = delta_b / ratio_b
        if units_a * units_b >= 0.0:
            continue

        paired = min(abs(units_a), abs(units_b))
        credit = q2(
            paired
            * float(spread["credit_per_unit"])
            * (1.0 - float(spread["rho"]))
        )
        credit_b = q2(credit / 2)
        credit_a = credit - credit_b
        if leg_a in credits:
            credits[leg_a] += credit_a
        if leg_b in credits:
            credits[leg_b] += credit_b
        residual[leg_a] = _toward_zero(delta_a, paired * ratio_a)
        residual[leg_b] = _toward_zero(delta_b, paired * ratio_b)

    for cc_id, state in states.items():
        state["inter_credit"] = q2(credits[cc_id])
        state["residual_delta"] = residual[cc_id]


def _float_money(value: Decimal) -> float:
    return 0.0 if value == 0 else float(value)


def compute_report(portfolio: dict, market: dict, config: dict) -> dict:
    valuation_date = date.fromisoformat(market["valuation_date"])
    net = net_positions(portfolio)

    by_cc: defaultdict[str, list[Position]] = defaultdict(list)
    for instrument_id, qty in net.items():
        position = _build_position(
            instrument_id, qty, market, config, valuation_date
        )
        cc_id = position.product_config["cc_id"]
        by_cc[cc_id].append(position)

    states: dict[str, dict] = {}
    cc_products = _representative_products(config)
    for cc_id in sorted(by_cc):
        positions = by_cc[cc_id]
        scenario_pl = [ZERO for _ in SCENARIOS]
        for position in positions:
            for scenario_index in range(len(SCENARIOS)):
                pnl, scenario_delta = _scenario_values(position, scenario_index)
                scenario_pl[scenario_index] += money(pnl)
                position.scenario_deltas.append(scenario_delta)

        worst_index = min(
            range(len(SCENARIOS)),
            key=lambda scenario_index: (scenario_pl[scenario_index], scenario_index),
        )
        scanning_risk = q2(max(Decimal(0), -scenario_pl[worst_index]))
        if worst_index < 14:
            second_index = min(
                (
                    scenario_index
                    for scenario_index in range(14)
                    if scenario_index != worst_index
                ),
                key=lambda scenario_index: (
                    scenario_pl[scenario_index],
                    scenario_index,
                ),
            )
        else:
            second_index = None

        bucket_deltas: defaultdict[str, float] = defaultdict(float)
        for position in positions:
            if second_index is None:
                composite_per_contract = position.scenario_deltas[worst_index]
            else:
                composite_per_contract = (
                    position.scenario_deltas[worst_index]
                    + position.scenario_deltas[second_index]
                ) / 2.0
            bucket_deltas[position.bucket] += position.qty * composite_per_contract

        representative = cc_products[cc_id][1]
        intra_charge, remaining = _intra_spread(
            dict(bucket_deltas), representative["intra_tiers"]
        )
        strip_credit = _strip_credit(
            remaining, float(representative["strip_rate"])
        )
        states[cc_id] = {
            "positions": positions,
            "config": representative,
            "scanning_risk": scanning_risk,
            "worst_scenario_id": worst_index + 1,
            "intra_charge": intra_charge,
            "remaining_buckets": remaining,
            "outright_delta": math.fsum(remaining.values()),
            "strip_credit": strip_credit,
        }

    _apply_inter_spreads(states, config, cc_products)

    rows: list[dict] = []
    total_margin_usd = ZERO
    for cc_id in sorted(states):
        state = states[cc_id]
        positions = state["positions"]
        product_config = state["config"]
        scanning_risk = state["scanning_risk"]
        som = _short_option_minimum(positions)
        nov_credit = _nov_credit(positions, scanning_risk)
        liquidity_addon = _liquidity_addon(positions)

        excess_delta = max(
            0.0,
            abs(state["residual_delta"])
            - float(product_config["concentration_threshold"]),
        )
        concentration_charge = q2(
            excess_delta * float(product_config["concentration_rate"])
        )
        raw_margin = q2(
            scanning_risk
            + state["intra_charge"]
            + concentration_charge
            - state["inter_credit"]
            - nov_credit
            - state["strip_credit"]
        )
        cc_margin_native = max(raw_margin, som) + liquidity_addon
        currency = product_config["currency"]
        cc_margin_usd = q2(
            cc_margin_native * _decimal(market["fx_to_usd"][currency])
        )
        total_margin_usd += cc_margin_usd

        rows.append(
            {
                "cc_id": cc_id,
                "currency": currency,
                "scanning_risk": _float_money(scanning_risk),
                "intra_charge": _float_money(state["intra_charge"]),
                "inter_credit": _float_money(state["inter_credit"]),
                "nov_credit": _float_money(nov_credit),
                "som": _float_money(som),
                "strip_credit": _float_money(state["strip_credit"]),
                "concentration_charge": _float_money(concentration_charge),
                "liquidity_addon": _float_money(liquidity_addon),
                "raw_margin": _float_money(raw_margin),
                "cc_margin_native": _float_money(cc_margin_native),
                "cc_margin_usd": _float_money(cc_margin_usd),
                "worst_scenario_id": state["worst_scenario_id"],
            }
        )

    return {
        "valuation_date": market["valuation_date"],
        "currency": "USD",
        "total_margin_usd": _float_money(q2(total_margin_usd)),
        "combined_commodities": rows,
    }


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def _render_json(value: Any, level: int = 0) -> str:
    """Render reports while retaining two fractional digits on money numbers."""

    indent = "  " * level
    child_indent = "  " * (level + 1)
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = [
            f"{child_indent}{json.dumps(str(key))}: {_render_json(item, level + 1)}"
            for key, item in value.items()
        ]
        return "{\n" + ",\n".join(items) + f"\n{indent}}}"
    if isinstance(value, list):
        if not value:
            return "[]"
        items = [f"{child_indent}{_render_json(item, level + 1)}" for item in value]
        return "[\n" + ",\n".join(items) + f"\n{indent}]"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (float, Decimal)):
        if not math.isfinite(float(value)):
            raise ValueError("non-finite number in margin report")
        return f"{value:.2f}"
    raise TypeError(f"cannot serialize {type(value).__name__}")


def write_report(report: dict, path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_render_json(report) + "\n")
