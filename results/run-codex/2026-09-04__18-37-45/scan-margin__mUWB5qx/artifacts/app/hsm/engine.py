"""House Scan Margin engine.

The calculation in this module follows ``docs/methodology.md``. Monetary
rounding is kept in :class:`~decimal.Decimal`; scenario P/L is deliberately
calculated in binary64 first because the methodology specifies that boundary.
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

from lib.black76 import delta as black_delta
from lib.black76 import price as black_price
from lib.black76 import year_fraction


CENT = Decimal("0.01")
ZERO_MONEY = Decimal("0.00")


@dataclass(frozen=True)
class Scenario:
    scenario_id: int
    price_multiplier: float
    vol_direction: int
    weight: float = 1.0


SCENARIOS = (
    Scenario(1, 0.0, 1),
    Scenario(2, 0.0, -1),
    Scenario(3, 1.0 / 3.0, 1),
    Scenario(4, 1.0 / 3.0, -1),
    Scenario(5, -1.0 / 3.0, 1),
    Scenario(6, -1.0 / 3.0, -1),
    Scenario(7, 2.0 / 3.0, 1),
    Scenario(8, 2.0 / 3.0, -1),
    Scenario(9, -2.0 / 3.0, 1),
    Scenario(10, -2.0 / 3.0, -1),
    Scenario(11, 1.0, 1),
    Scenario(12, 1.0, -1),
    Scenario(13, -1.0, 1),
    Scenario(14, -1.0, -1),
    Scenario(15, 3.0, 1, 0.28),
    Scenario(16, -3.0, -1, 0.28),
)

# Retained as a public constant for compatibility with the original module.
PRICE_MULT = [scenario.price_multiplier for scenario in SCENARIOS]

_OPTION_RE = re.compile(
    r"^(?P<product>.+)-(?P<year>\d{4})-(?P<month>\d{2})-"
    r"(?P<put_call>[CP])-(?P<strike>[+-]?\d+\.\d{2})$"
)
_FUTURE_RE = re.compile(
    r"^(?P<product>.+)-(?P<year>\d{4})-(?P<month>\d{2})$"
)


@dataclass(frozen=True)
class Instrument:
    instrument_id: str
    product: str
    year: int
    month: int
    put_call: str | None = None
    strike: float | None = None

    @property
    def is_option(self) -> bool:
        return self.put_call is not None

    @property
    def is_call(self) -> bool:
        return self.put_call == "C"

    @property
    def bucket(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    @property
    def underlying_id(self) -> str:
        return f"{self.product}-{self.bucket}"


@dataclass
class PositionState:
    instrument: Instrument
    qty: float
    product_config: dict[str, Any]
    forward: float
    multiplier: float
    atm_delta: float
    unshocked_value: float
    scenario_deltas: list[float]


def q2(value: Decimal | float | int) -> Decimal:
    """Round a monetary result to cents using decimal half-even."""

    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    rounded = value.quantize(CENT, rounding=ROUND_HALF_EVEN)
    return ZERO_MONEY if rounded == 0 else rounded


def money(value: float) -> Decimal:
    """Apply the methodology's special position-scenario P/L rounding."""

    rounded = Decimal(format(float(value), ".10f")).quantize(
        CENT, rounding=ROUND_HALF_EVEN
    )
    return ZERO_MONEY if rounded == 0 else rounded


def _as_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def net_positions(portfolio: dict[str, Any]) -> dict[str, float]:
    """Net duplicate rows exactly before converting quantities to binary64."""

    quantities: dict[str, Decimal] = defaultdict(Decimal)
    for row in portfolio["positions"]:
        quantities[row["instrument_id"]] += _as_decimal(row["qty"])
    return {
        instrument_id: float(quantity)
        for instrument_id, quantity in quantities.items()
        if quantity != 0
    }


def parse_instrument(instrument_id: str) -> Instrument:
    option_match = _OPTION_RE.fullmatch(instrument_id)
    if option_match:
        fields = option_match.groupdict()
        return Instrument(
            instrument_id=instrument_id,
            product=fields["product"],
            year=int(fields["year"]),
            month=int(fields["month"]),
            put_call=fields["put_call"],
            strike=float(fields["strike"]),
        )

    future_match = _FUTURE_RE.fullmatch(instrument_id)
    if future_match:
        fields = future_match.groupdict()
        return Instrument(
            instrument_id=instrument_id,
            product=fields["product"],
            year=int(fields["year"]),
            month=int(fields["month"]),
        )
    raise ValueError(f"invalid instrument_id: {instrument_id!r}")


def product_of(instrument_id: str) -> str:
    return parse_instrument(instrument_id).product


def is_option(instrument_id: str) -> bool:
    return parse_instrument(instrument_id).is_option


def _effective_psr(
    instrument: Instrument,
    forward: float,
    product_config: dict[str, Any],
    house_config: dict[str, Any],
    valuation_date: date,
) -> float:
    delivery_date = date(instrument.year, instrument.month, 1)
    delivery_days = (delivery_date - valuation_date).days
    if delivery_days <= int(house_config["delivery_scale_days"]):
        scale = 1.0
    else:
        scale = max(
            math.sqrt(delivery_days / 365.0),
            float(house_config["delivery_scale_floor"]),
        )
    return float(product_config["price_scan_range"]) * scale


def _shocked_forward(
    forward: float,
    price_multiplier: float,
    effective_psr: float,
    shock_mode: str,
) -> float:
    if shock_mode == "linear":
        shocked = forward + price_multiplier * effective_psr
    elif forward > 0.0:
        shocked = forward * math.exp(price_multiplier * effective_psr / forward)
    else:
        shocked = 1e-8
    return max(shocked, 1e-8)


def _position_state(
    instrument: Instrument,
    qty: float,
    product_config: dict[str, Any],
    house_config: dict[str, Any],
    market: dict[str, Any],
    valuation_date: date,
) -> tuple[PositionState, list[Decimal]]:
    forward = float(market["futures_price"][instrument.underlying_id])
    multiplier = float(product_config["multiplier"])
    effective_psr = _effective_psr(
        instrument, forward, product_config, house_config, valuation_date
    )

    if instrument.is_option:
        strike = float(instrument.strike)
        volatility = float(market["atm_vol"][instrument.instrument_id])
        expiry = date.fromisoformat(market["option_expiry"][instrument.instrument_id])
        time_to_expiry = year_fraction(valuation_date, expiry)
        unshocked_value = black_price(
            forward, strike, volatility, time_to_expiry, instrument.is_call
        )
        atm_delta = black_delta(
            forward, strike, volatility, time_to_expiry, instrument.is_call
        )
    else:
        strike = 0.0
        volatility = 0.0
        time_to_expiry = 0.0
        unshocked_value = 0.0
        # Quantity carries the long/short sign for futures.
        atm_delta = 1.0

    scenario_deltas: list[float] = []
    scenario_pl: list[Decimal] = []
    for scenario in SCENARIOS:
        shocked_forward = _shocked_forward(
            forward,
            scenario.price_multiplier,
            effective_psr,
            product_config["shock_mode"],
        )
        if instrument.is_option:
            fraction = (
                float(product_config["vol_scan_fraction"])
                if scenario.vol_direction > 0
                else -float(product_config["vsf_down"])
            )
            shocked_volatility = max(volatility * (1.0 + fraction), 1e-6)
            shocked_value = black_price(
                shocked_forward,
                strike,
                shocked_volatility,
                time_to_expiry,
                instrument.is_call,
            )
            per_contract_delta = black_delta(
                shocked_forward,
                strike,
                shocked_volatility,
                time_to_expiry,
                instrument.is_call,
            )
            raw_pl = (
                qty
                * (shocked_value - unshocked_value)
                * multiplier
                * scenario.weight
            )
        else:
            per_contract_delta = 1.0
            raw_pl = (
                qty
                * (shocked_forward - forward)
                * multiplier
                * scenario.weight
            )
        scenario_deltas.append(per_contract_delta)
        scenario_pl.append(money(raw_pl))

    return (
        PositionState(
            instrument=instrument,
            qty=qty,
            product_config=product_config,
            forward=forward,
            multiplier=multiplier,
            atm_delta=atm_delta,
            unshocked_value=unshocked_value,
            scenario_deltas=scenario_deltas,
        ),
        scenario_pl,
    )


def _month_start(bucket: str) -> date:
    year, month = bucket.split("-")
    return date(int(year), int(month), 1)


def _month_number(bucket: str) -> int:
    year, month = bucket.split("-")
    return int(year) * 12 + int(month) - 1


def _intra_spread(
    bucket_deltas: dict[str, float], product_config: dict[str, Any]
) -> tuple[Decimal, dict[str, float]]:
    remaining = dict(bucket_deltas)
    charges: list[float] = []
    tiers = product_config["intra_tiers"]

    while True:
        active = [bucket for bucket, delta in remaining.items() if delta != 0.0]
        if not active:
            break
        bucket_a = min(active, key=lambda bucket: (-abs(remaining[bucket]), bucket))
        delta_a = remaining[bucket_a]
        opposites = [
            bucket for bucket in active if remaining[bucket] * delta_a < 0.0
        ]
        if not opposites:
            break

        date_a = _month_start(bucket_a)

        def opposite_key(bucket: str) -> tuple[int, float, str]:
            distance = abs((_month_start(bucket) - date_a).days)
            return distance, -abs(remaining[bucket]), bucket

        bucket_b = min(opposites, key=opposite_key)
        delta_b = remaining[bucket_b]
        matched = min(abs(delta_a), abs(delta_b))
        distance = abs((_month_start(bucket_b) - date_a).days)
        if distance <= 32:
            rate = float(tiers["adjacent"])
        elif distance <= 125:
            rate = float(tiers["mid"])
        else:
            rate = float(tiers["back"])
        charges.append(matched * rate * math.sqrt(distance / 365.0))

        remaining[bucket_a] = math.copysign(
            max(0.0, abs(delta_a) - matched), delta_a
        )
        remaining[bucket_b] = math.copysign(
            max(0.0, abs(delta_b) - matched), delta_b
        )
        # Avoid negative zero acting like a signed exposure in later logic.
        if abs(delta_a) == matched:
            remaining[bucket_a] = 0.0
        if abs(delta_b) == matched:
            remaining[bucket_b] = 0.0

    return q2(math.fsum(charges)), remaining


def _strip_credit(
    remaining: dict[str, float], product_config: dict[str, Any]
) -> Decimal:
    strip_rate = float(product_config["strip_rate"])
    if strip_rate == 0.0:
        return ZERO_MONEY

    active = sorted(bucket for bucket, delta in remaining.items() if delta != 0.0)
    if len(active) < 3:
        return ZERO_MONEY

    runs: list[list[str]] = []
    run: list[str] = []
    for bucket in active:
        if run and _month_number(bucket) != _month_number(run[-1]) + 1:
            runs.append(run)
            run = []
        run.append(bucket)
    if run:
        runs.append(run)

    credits = [
        (len(months) - 2)
        * strip_rate
        * min(abs(remaining[bucket]) for bucket in months)
        for months in runs
        if len(months) >= 3
    ]
    return q2(math.fsum(credits))


def _cc_product_config(
    cc_id: str, products: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Return the CC's product settings (the methodology defines one set/CC)."""

    product_names = sorted(
        product_name
        for product_name, product_config in products.items()
        if product_config["cc_id"] == cc_id
    )
    if not product_names:
        raise KeyError(f"no product configured for combined commodity {cc_id!r}")
    return products[product_names[0]]


def _valid_inter_pair(
    spread: dict[str, Any], cc_configs: dict[str, dict[str, Any]]
) -> bool:
    leg_a = spread["leg_a"]
    leg_b = spread["leg_b"]
    if leg_a not in cc_configs or leg_b not in cc_configs:
        return False
    config_a = cc_configs[leg_a]
    config_b = cc_configs[leg_b]
    return (
        config_a["ics_group"] == config_b["ics_group"]
        and config_a["ics_group"] == spread["ics_group"]
        and config_a["currency"] == config_b["currency"]
    )


def _apply_inter_spreads(
    outright_deltas: dict[str, float],
    spreads: list[dict[str, Any]],
    cc_configs: dict[str, dict[str, Any]],
) -> tuple[dict[str, Decimal], dict[str, float]]:
    residual = dict(outright_deltas)
    credits = {cc_id: ZERO_MONEY for cc_id in outright_deltas}

    for spread in sorted(spreads, key=lambda row: int(row["priority"])):
        if not _valid_inter_pair(spread, cc_configs):
            continue
        leg_a = spread["leg_a"]
        leg_b = spread["leg_b"]
        if leg_a not in residual or leg_b not in residual:
            continue
        delta_a = residual[leg_a]
        delta_b = residual[leg_b]
        if delta_a == 0.0 or delta_b == 0.0:
            continue

        ratio_a = float(spread["ratio_a"])
        ratio_b = float(spread["ratio_b"])
        units_a = delta_a / ratio_a
        units_b = delta_b / ratio_b
        if units_a * units_b >= 0.0:
            continue

        paired = min(abs(units_a), abs(units_b))
        total_credit = q2(
            paired
            * float(spread["credit_per_unit"])
            * (1.0 - float(spread["rho"]))
        )
        credit_b = q2(total_credit / 2)
        credit_a = total_credit - credit_b
        credits[leg_a] += credit_a
        credits[leg_b] += credit_b

        if abs(units_a) == paired:
            residual[leg_a] = 0.0
        else:
            residual[leg_a] = math.copysign(
                max(0.0, abs(delta_a) - paired * abs(ratio_a)), delta_a
            )
        if abs(units_b) == paired:
            residual[leg_b] = 0.0
        else:
            residual[leg_b] = math.copysign(
                max(0.0, abs(delta_b) - paired * abs(ratio_b)), delta_b
            )

    return credits, residual


def compute_report(
    portfolio: dict[str, Any], market: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    net = net_positions(portfolio)
    product_configs = config["products"]
    valuation_date = date.fromisoformat(market["valuation_date"])

    positions_by_cc: dict[str, list[tuple[Instrument, float]]] = defaultdict(list)
    for instrument_id, qty in net.items():
        instrument = parse_instrument(instrument_id)
        cc_id = product_configs[instrument.product]["cc_id"]
        positions_by_cc[cc_id].append((instrument, qty))

    # First perform the core scan and the intra-commodity work independently
    # for each non-empty CC.
    calculations: dict[str, dict[str, Any]] = {}
    cc_configs = {
        cc_id: _cc_product_config(cc_id, product_configs)
        for cc_id in positions_by_cc
    }
    for cc_id in sorted(positions_by_cc):
        cc_positions = sorted(
            positions_by_cc[cc_id], key=lambda item: item[0].instrument_id
        )
        states: list[PositionState] = []
        cc_pl = [ZERO_MONEY for _ in SCENARIOS]

        for instrument, qty in cc_positions:
            product_config = product_configs[instrument.product]
            state, position_pl = _position_state(
                instrument,
                qty,
                product_config,
                config["house"],
                market,
                valuation_date,
            )
            states.append(state)
            for index, value in enumerate(position_pl):
                cc_pl[index] += value

        worst_index = min(range(16), key=lambda index: (cc_pl[index], index))
        worst_scenario_id = worst_index + 1
        scanning_risk = max(ZERO_MONEY, -cc_pl[worst_index])

        if worst_scenario_id <= 14:
            second_index = min(
                (index for index in range(14) if index != worst_index),
                key=lambda index: (cc_pl[index], index),
            )
        else:
            second_index = None

        bucket_deltas: dict[str, float] = defaultdict(float)
        for state in states:
            if second_index is None:
                composite_per_contract = state.scenario_deltas[worst_index]
            else:
                composite_per_contract = (
                    state.scenario_deltas[worst_index]
                    + state.scenario_deltas[second_index]
                ) / 2.0
            bucket_deltas[state.instrument.bucket] += (
                composite_per_contract * state.qty
            )

        cc_product_config = cc_configs[cc_id]
        intra_charge, remaining = _intra_spread(
            dict(bucket_deltas), cc_product_config
        )
        strip_credit = _strip_credit(remaining, cc_product_config)
        outright_delta = math.fsum(remaining.values())

        som_contributions: list[float] = []
        nov_contributions: list[float] = []
        lao_contributions: list[float] = []
        for state in states:
            if not state.instrument.is_option:
                continue
            absolute_delta = abs(state.atm_delta)
            if state.qty < 0.0:
                som_contributions.append(
                    float(state.product_config["som_rate"])
                    * abs(state.qty)
                    * (1.0 + max(0.0, 0.25 - absolute_delta))
                )
                lao_contributions.append(
                    float(state.product_config["lao_rate"])
                    * abs(state.qty)
                    * max(
                        0.0,
                        float(state.product_config["lao_otm"]) - absolute_delta,
                    )
                )
            elif state.qty > 0.0 and absolute_delta < 0.35:
                nov_contributions.append(
                    max(
                        0.0,
                        state.qty * state.unshocked_value * state.multiplier,
                    )
                )

        calculations[cc_id] = {
            "scanning_risk": scanning_risk,
            "intra_charge": intra_charge,
            "strip_credit": strip_credit,
            "outright_delta": outright_delta,
            "som": q2(math.fsum(som_contributions)),
            "nov": math.fsum(nov_contributions),
            "liquidity_addon": q2(math.fsum(lao_contributions)),
            "worst_scenario_id": worst_scenario_id,
        }

    inter_credits, residual_deltas = _apply_inter_spreads(
        {
            cc_id: calculation["outright_delta"]
            for cc_id, calculation in calculations.items()
        },
        config["inter_spreads"],
        cc_configs,
    )

    rows: list[dict[str, Any]] = []
    total_margin_usd = ZERO_MONEY
    for cc_id in sorted(calculations):
        calculation = calculations[cc_id]
        cc_product_config = cc_configs[cc_id]
        scanning_risk = calculation["scanning_risk"]
        nov_credit = q2(min(_as_decimal(calculation["nov"]), scanning_risk))
        concentration_charge = q2(
            max(
                0.0,
                abs(residual_deltas[cc_id])
                - float(cc_product_config["concentration_threshold"]),
            )
            * float(cc_product_config["concentration_rate"])
        )
        inter_credit = inter_credits[cc_id]
        raw_margin = q2(
            scanning_risk
            + calculation["intra_charge"]
            + concentration_charge
            - inter_credit
            - nov_credit
            - calculation["strip_credit"]
        )
        margin_before_liquidity = max(raw_margin, calculation["som"])
        cc_margin_native = margin_before_liquidity + calculation["liquidity_addon"]
        currency = cc_product_config["currency"]
        cc_margin_usd = q2(
            cc_margin_native * _as_decimal(market["fx_to_usd"][currency])
        )
        total_margin_usd += cc_margin_usd

        rows.append(
            {
                "cc_id": cc_id,
                "currency": currency,
                "scanning_risk": scanning_risk,
                "intra_charge": calculation["intra_charge"],
                "inter_credit": inter_credit,
                "nov_credit": nov_credit,
                "som": calculation["som"],
                "strip_credit": calculation["strip_credit"],
                "concentration_charge": concentration_charge,
                "liquidity_addon": calculation["liquidity_addon"],
                "raw_margin": raw_margin,
                "cc_margin_native": cc_margin_native,
                "cc_margin_usd": cc_margin_usd,
                "worst_scenario_id": calculation["worst_scenario_id"],
            }
        )

    return {
        "valuation_date": market["valuation_date"],
        "currency": "USD",
        "total_margin_usd": total_margin_usd,
        "combined_commodities": rows,
    }


def load_json(path: str | Path) -> dict[str, Any]:
    # Preserve input decimal values until a calculation explicitly calls for
    # binary64 (scenario valuation and deltas).
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_float=Decimal)


def _render_json(value: Any, level: int = 0) -> str:
    """Pretty-print JSON while retaining two decimal places on money numbers."""

    indent = "  " * level
    child_indent = "  " * (level + 1)
    if isinstance(value, Decimal):
        return format(value, ".2f")
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = [
            f"{child_indent}{json.dumps(key)}: {_render_json(item, level + 1)}"
            for key, item in value.items()
        ]
        return "{\n" + ",\n".join(items) + f"\n{indent}}}"
    if isinstance(value, list):
        if not value:
            return "[]"
        items = [f"{child_indent}{_render_json(item, level + 1)}" for item in value]
        return "[\n" + ",\n".join(items) + f"\n{indent}]"
    return json.dumps(value)


def write_report(report: dict[str, Any], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_render_json(report) + "\n", encoding="utf-8")
