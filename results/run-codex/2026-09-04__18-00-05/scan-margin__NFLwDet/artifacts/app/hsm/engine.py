"""House Scan Margin calculation engine.

The public interface is the CLI in :mod:`run_margin`; this module contains the
calculation and the deliberately small amount of JSON I/O it needs.
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path
from typing import Any

from lib.black76 import delta as black76_delta
from lib.black76 import price as black76_price
from lib.black76 import year_fraction

CENT = Decimal("0.01")


@dataclass(frozen=True)
class Scenario:
    price_multiplier: float
    vol_direction: float
    weight: float = 1.0


# The order is the scenario id (index + 1), and is therefore significant.
SCENARIOS = (
    Scenario(0.0, 1.0),
    Scenario(0.0, -1.0),
    Scenario(1.0 / 3.0, 1.0),
    Scenario(1.0 / 3.0, -1.0),
    Scenario(-1.0 / 3.0, 1.0),
    Scenario(-1.0 / 3.0, -1.0),
    Scenario(2.0 / 3.0, 1.0),
    Scenario(2.0 / 3.0, -1.0),
    Scenario(-2.0 / 3.0, 1.0),
    Scenario(-2.0 / 3.0, -1.0),
    Scenario(1.0, 1.0),
    Scenario(1.0, -1.0),
    Scenario(-1.0, 1.0),
    Scenario(-1.0, -1.0),
    Scenario(3.0, 1.0, 0.28),
    Scenario(-3.0, -1.0, 0.28),
)

_INSTRUMENT_RE = re.compile(
    r"^(?P<product>.+)-(?P<year>\d{4})-(?P<month>\d{2})"
    r"(?:-(?P<option_type>[CP])-(?P<strike>-?\d+\.\d{2}))?$"
)


@dataclass(frozen=True)
class Instrument:
    instrument_id: str
    product: str
    month: str
    option_type: str | None = None
    strike: float | None = None

    @property
    def is_option(self) -> bool:
        return self.option_type is not None

    @property
    def underlying_id(self) -> str:
        return f"{self.product}-{self.month}"


@dataclass
class Position:
    instrument: Instrument
    qty: float
    product_config: dict[str, Any]
    forward: float
    atm_vol: float | None = None
    time_to_expiry: float | None = None
    base_value: float = 0.0
    atm_delta: float = 1.0
    scenario_deltas: list[float] = field(default_factory=list)


@dataclass
class CCState:
    cc_id: str
    currency: str
    ics_group: str
    product_config: dict[str, Any]
    positions: list[Position]
    scenario_pl: list[Decimal] = field(default_factory=list)
    scanning_risk: Decimal = Decimal("0.00")
    worst_scenario_id: int = 1
    intra_charge: Decimal = Decimal("0.00")
    outright_delta: float = 0.0
    inter_credit: Decimal = Decimal("0.00")
    nov_credit: Decimal = Decimal("0.00")
    som: Decimal = Decimal("0.00")


def _as_decimal(value: Decimal | int | float | str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def q2(value: Decimal | int | float | str) -> Decimal:
    """Round a decimal value to cents using round-half-to-even."""

    value = _as_decimal(value)
    # Decimal's default precision is not part of HSM. Make quantization work
    # for large (but otherwise valid) JSON numbers as well.
    digits = len(value.as_tuple().digits)
    with localcontext() as context:
        context.prec = max(34, digits + abs(value.as_tuple().exponent) + 4)
        rounded = value.quantize(CENT, rounding=ROUND_HALF_EVEN)
    # A zero monetary amount is not a loss and should never leak as -0.00.
    return Decimal("0.00") if rounded == 0 else rounded


def scenario_money(value: float) -> Decimal:
    """Apply the methodology's binary64 -> 10dp -> cents conversion."""

    return q2(Decimal(format(float(value), ".10f")))


def _round_float_money(value: float) -> Decimal:
    """Round a completed binary64 monetary calculation to cents."""

    return q2(Decimal(str(float(value))))


def net_positions(portfolio: dict[str, Any]) -> dict[str, Decimal]:
    """Net duplicate rows using their decimal JSON values before valuation."""

    quantities: dict[str, Decimal] = defaultdict(Decimal)
    for row in portfolio["positions"]:
        quantities[row["instrument_id"]] += _as_decimal(row["qty"])
    return {iid: qty for iid, qty in quantities.items() if qty != 0}


def parse_instrument(instrument_id: str) -> Instrument:
    match = _INSTRUMENT_RE.fullmatch(instrument_id)
    if match is None:
        raise ValueError(f"invalid instrument_id: {instrument_id!r}")
    month_number = int(match.group("month"))
    if not 1 <= month_number <= 12:
        raise ValueError(f"invalid contract month in instrument_id: {instrument_id!r}")
    option_type = match.group("option_type")
    strike_text = match.group("strike")
    return Instrument(
        instrument_id=instrument_id,
        product=match.group("product"),
        month=f'{match.group("year")}-{match.group("month")}',
        option_type=option_type,
        strike=float(strike_text) if strike_text is not None else None,
    )


def _build_positions(
    portfolio: dict[str, Any], market: dict[str, Any], config: dict[str, Any]
) -> dict[str, list[Position]]:
    valuation_date = date.fromisoformat(market["valuation_date"])
    products = config["products"]
    by_cc: dict[str, list[Position]] = defaultdict(list)

    # Distinct position rows are mathematically unordered. Canonicalizing them
    # also makes later binary64 delta sums independent of portfolio row order.
    for instrument_id, decimal_qty in sorted(net_positions(portfolio).items()):
        instrument = parse_instrument(instrument_id)
        if instrument.product not in products:
            raise KeyError(f"no config for product {instrument.product!r}")
        product_config = products[instrument.product]
        forward = float(market["futures_price"][instrument.underlying_id])
        position = Position(
            instrument=instrument,
            qty=float(decimal_qty),
            product_config=product_config,
            forward=forward,
        )

        if instrument.is_option:
            vol = float(market["atm_vol"][instrument_id])
            expiry = date.fromisoformat(market["option_expiry"][instrument_id])
            time_to_expiry = year_fraction(valuation_date, expiry)
            strike = instrument.strike
            assert strike is not None
            is_call = instrument.option_type == "C"
            position.atm_vol = vol
            position.time_to_expiry = time_to_expiry
            position.base_value = black76_price(
                forward, strike, vol, time_to_expiry, is_call
            )
            position.atm_delta = black76_delta(
                forward, strike, vol, time_to_expiry, is_call
            )

        by_cc[product_config["cc_id"]].append(position)

    return by_cc


def _cc_metadata(config: dict[str, Any]) -> dict[str, dict[str, set[str]]]:
    """Collect metadata for active and inactive CCs for spread validation."""

    metadata: dict[str, dict[str, set[str]]] = {}
    for product in config["products"].values():
        cc_id = product["cc_id"]
        item = metadata.setdefault(cc_id, {"currencies": set(), "groups": set()})
        item["currencies"].add(product["currency"])
        item["groups"].add(product["ics_group"])
    return metadata


def _scenario_value_and_delta(
    position: Position, scenario: Scenario
) -> tuple[float, float]:
    """Return raw weighted position P/L and per-contract scenario delta."""

    config = position.product_config
    price_change = scenario.price_multiplier * float(config["price_scan_range"])
    multiplier = float(config["multiplier"])

    if not position.instrument.is_option:
        # Retain the specified F' = F + shock, then F' - F operation order.
        shocked_forward = position.forward + price_change
        raw_pl = (
            position.qty
            * (shocked_forward - position.forward)
            * multiplier
            * scenario.weight
        )
        return raw_pl, 1.0

    strike = position.instrument.strike
    vol = position.atm_vol
    time_to_expiry = position.time_to_expiry
    assert strike is not None and vol is not None and time_to_expiry is not None
    shocked_forward = max(position.forward + price_change, 1.0e-8)
    shocked_vol = max(
        vol * (1.0 + scenario.vol_direction * float(config["vol_scan_fraction"])),
        1.0e-6,
    )
    is_call = position.instrument.option_type == "C"
    shocked_value = black76_price(
        shocked_forward, strike, shocked_vol, time_to_expiry, is_call
    )
    scenario_delta = black76_delta(
        shocked_forward, strike, shocked_vol, time_to_expiry, is_call
    )
    raw_pl = (
        position.qty
        * (shocked_value - position.base_value)
        * multiplier
        * scenario.weight
    )
    return raw_pl, scenario_delta


def _calculate_scenarios(state: CCState) -> None:
    scenario_pl = [Decimal("0.00") for _ in SCENARIOS]
    for position in state.positions:
        deltas: list[float] = []
        for index, scenario in enumerate(SCENARIOS):
            raw_pl, delta = _scenario_value_and_delta(position, scenario)
            scenario_pl[index] += scenario_money(raw_pl)
            deltas.append(delta)
        position.scenario_deltas = deltas

    worst_index = min(range(len(SCENARIOS)), key=lambda i: (scenario_pl[i], i))
    state.scenario_pl = scenario_pl
    state.worst_scenario_id = worst_index + 1
    state.scanning_risk = max(Decimal("0.00"), -scenario_pl[worst_index])


def _composite_buckets(state: CCState) -> dict[str, float]:
    worst_index = state.worst_scenario_id - 1
    if worst_index < 14:
        next_worst_index = min(
            (i for i in range(14) if i != worst_index),
            key=lambda i: (state.scenario_pl[i], i),
        )
    else:
        next_worst_index = None

    buckets: dict[str, float] = defaultdict(float)
    for position in state.positions:
        if next_worst_index is None:
            per_contract_delta = position.scenario_deltas[worst_index]
        else:
            per_contract_delta = (
                position.scenario_deltas[worst_index]
                + position.scenario_deltas[next_worst_index]
            ) / 2.0
        buckets[position.instrument.month] += position.qty * per_contract_delta
    return dict(buckets)


def _month_start(month: str) -> date:
    year_text, month_text = month.split("-")
    return date(int(year_text), int(month_text), 1)


def _intra_spread(
    bucket_deltas: dict[str, float], tiers: dict[str, Any]
) -> tuple[Decimal, float]:
    remaining = dict(bucket_deltas)
    month_dates = {month: _month_start(month) for month in remaining}
    total_charge = 0.0

    while True:
        nonzero = [month for month, value in remaining.items() if value != 0.0]
        has_positive = any(remaining[month] > 0.0 for month in nonzero)
        has_negative = any(remaining[month] < 0.0 for month in nonzero)
        if not (has_positive and has_negative):
            break

        # min with a negated magnitude implements largest absolute delta, then
        # lexicographically earliest month.
        leg_a = min(nonzero, key=lambda month: (-abs(remaining[month]), month))
        value_a = remaining[leg_a]
        opposite = [
            month for month in nonzero if remaining[month] * value_a < 0.0
        ]
        leg_b = min(
            opposite,
            key=lambda month: (
                abs((month_dates[leg_a] - month_dates[month]).days),
                -abs(remaining[month]),
                month,
            ),
        )

        value_b = remaining[leg_b]
        matched = min(abs(value_a), abs(value_b))
        distance = abs((month_dates[leg_a] - month_dates[leg_b]).days)
        if distance <= 32:
            rate = float(tiers["adjacent"])
        elif distance <= 125:
            rate = float(tiers["mid"])
        else:
            rate = float(tiers["back"])
        total_charge += matched * rate * math.sqrt(distance / 365.0)

        remaining_a = abs(value_a) - matched
        remaining_b = abs(value_b) - matched
        remaining[leg_a] = (
            math.copysign(remaining_a, value_a) if remaining_a != 0.0 else 0.0
        )
        remaining[leg_b] = (
            math.copysign(remaining_b, value_b) if remaining_b != 0.0 else 0.0
        )

    # The methodology explicitly characterizes this as a charge, never a
    # credit, including at the final monetary rounding step.
    return _round_float_money(max(0.0, total_charge)), sum(remaining.values())


def _calculate_som_and_nov(state: CCState) -> None:
    som = 0.0
    nov = 0.0
    for position in state.positions:
        if not position.instrument.is_option:
            continue
        if position.qty < 0.0:
            som += (
                float(position.product_config["som_rate"])
                * abs(position.qty)
                * (1.0 + max(0.0, 0.25 - abs(position.atm_delta)))
            )
        elif position.qty > 0.0 and abs(position.atm_delta) < 0.35:
            nov += max(
                0.0,
                position.qty
                * position.base_value
                * float(position.product_config["multiplier"]),
            )
    state.som = _round_float_money(som)
    state.nov_credit = _round_float_money(nov)


def _make_states(
    by_cc: dict[str, list[Position]], config: dict[str, Any]
) -> dict[str, CCState]:
    states: dict[str, CCState] = {}
    for cc_id, positions in by_cc.items():
        # A CC has one currency/group and one intra table by methodology. A
        # stable product choice avoids making the result depend on portfolio row
        # order when a coherent config maps multiple products to the same CC.
        representative = min(positions, key=lambda p: p.instrument.product)
        product_config = representative.product_config
        state = CCState(
            cc_id=cc_id,
            currency=product_config["currency"],
            ics_group=product_config["ics_group"],
            product_config=product_config,
            positions=positions,
        )
        _calculate_scenarios(state)
        buckets = _composite_buckets(state)
        state.intra_charge, state.outright_delta = _intra_spread(
            buckets, product_config["intra_tiers"]
        )
        _calculate_som_and_nov(state)
        states[cc_id] = state
    return states


def _opposite_sign(a: float, b: float) -> bool:
    return (a < 0.0 < b) or (b < 0.0 < a)


def _reduce_units_toward_zero(units: float, paired: float) -> float:
    residual = abs(units) - paired
    return math.copysign(residual, units) if residual != 0.0 else 0.0


def _apply_inter_spreads(
    states: dict[str, CCState], config: dict[str, Any]
) -> None:
    metadata = _cc_metadata(config)
    for spread in sorted(config["inter_spreads"], key=lambda item: item["priority"]):
        leg_a = spread["leg_a"]
        leg_b = spread["leg_b"]
        if leg_a == leg_b or leg_a not in metadata or leg_b not in metadata:
            continue

        meta_a = metadata[leg_a]
        meta_b = metadata[leg_b]
        spread_group = spread["ics_group"]
        valid_group = (
            meta_a["groups"] == {spread_group}
            and meta_b["groups"] == {spread_group}
        )
        valid_currency = (
            len(meta_a["currencies"]) == 1
            and meta_a["currencies"] == meta_b["currencies"]
        )
        if not (valid_group and valid_currency):
            continue
        if leg_a not in states or leg_b not in states:
            continue

        state_a = states[leg_a]
        state_b = states[leg_b]
        ratio_a = float(spread["ratio_a"])
        ratio_b = float(spread["ratio_b"])
        if ratio_a == 0.0 or ratio_b == 0.0:
            raise ValueError("inter-spread ratios must be non-zero")
        units_a = state_a.outright_delta / ratio_a
        units_b = state_b.outright_delta / ratio_b
        if not (
            _opposite_sign(state_a.outright_delta, state_b.outright_delta)
            and _opposite_sign(units_a, units_b)
        ):
            continue

        paired = min(abs(units_a), abs(units_b))
        credit_float = paired * float(spread["credit_per_unit"])
        total_credit = Decimal(str(credit_float))
        credit_b = _round_float_money(credit_float / 2.0)
        credit_a = total_credit - credit_b
        state_a.inter_credit += credit_a
        state_b.inter_credit += credit_b

        state_a.outright_delta = (
            _reduce_units_toward_zero(units_a, paired) * ratio_a
        )
        state_b.outright_delta = (
            _reduce_units_toward_zero(units_b, paired) * ratio_b
        )


def compute_report(
    portfolio: dict[str, Any], market: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    by_cc = _build_positions(portfolio, market, config)
    states = _make_states(by_cc, config)
    _apply_inter_spreads(states, config)
    fx = {currency: _as_decimal(rate) for currency, rate in market["fx_to_usd"].items()}

    rows: list[dict[str, Any]] = []
    total = Decimal("0.00")
    for cc_id in sorted(states):
        state = states[cc_id]
        raw_margin = q2(
            state.scanning_risk
            + state.intra_charge
            - state.inter_credit
            - state.nov_credit
        )
        cc_margin_native = max(raw_margin, state.som)
        cc_margin_usd = q2(cc_margin_native * fx[state.currency])
        total += cc_margin_usd
        rows.append(
            {
                "cc_id": cc_id,
                "currency": state.currency,
                "scanning_risk": q2(state.scanning_risk),
                "intra_charge": q2(state.intra_charge),
                "inter_credit": q2(state.inter_credit),
                "nov_credit": q2(state.nov_credit),
                "som": q2(state.som),
                "raw_margin": raw_margin,
                "cc_margin_native": cc_margin_native,
                "cc_margin_usd": cc_margin_usd,
                "worst_scenario_id": state.worst_scenario_id,
            }
        )

    return {
        "valuation_date": market["valuation_date"],
        "currency": "USD",
        "total_margin_usd": total,
        "combined_commodities": rows,
    }


def load_json(path: str | Path) -> dict[str, Any]:
    # parse_float=Decimal preserves fractional quantities for exact pre-valuation
    # netting. Pricing explicitly converts the completed net quantity to float.
    with Path(path).open(encoding="utf-8") as input_file:
        return json.load(input_file, parse_float=Decimal)


def _render_json(value: Any, level: int = 0) -> str:
    """Render JSON while retaining the required two decimal money lexemes."""

    if isinstance(value, Decimal):
        return format(q2(value), ".2f")
    if isinstance(value, dict):
        if not value:
            return "{}"
        lines = ["{"]
        items = list(value.items())
        for index, (key, item) in enumerate(items):
            comma = "," if index + 1 < len(items) else ""
            lines.append(
                "  " * (level + 1)
                + json.dumps(str(key))
                + ": "
                + _render_json(item, level + 1)
                + comma
            )
        lines.append("  " * level + "}")
        return "\n".join(lines)
    if isinstance(value, list):
        if not value:
            return "[]"
        lines = ["["]
        for index, item in enumerate(value):
            comma = "," if index + 1 < len(value) else ""
            lines.append(
                "  " * (level + 1) + _render_json(item, level + 1) + comma
            )
        lines.append("  " * level + "]")
        return "\n".join(lines)
    return json.dumps(value)


def write_report(report: dict[str, Any], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_render_json(report) + "\n", encoding="utf-8")
