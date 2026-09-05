"""House Scan Margin engine.

The implementation in this module follows ``docs/methodology.md``. All
valuation calculations are binary64; amounts that the methodology defines as
money are carried as :class:`~decimal.Decimal` after the prescribed rounding.
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

try:  # Support both the CLI's direct import and ``import hsm.engine``.
    from .lib.black76 import delta as black_delta
    from .lib.black76 import price as black_price
    from .lib.black76 import year_fraction
except ImportError:  # pragma: no cover - this is the path used by run_margin.py
    from lib.black76 import delta as black_delta
    from lib.black76 import price as black_price
    from lib.black76 import year_fraction


CENT = Decimal("0.01")


@dataclass(frozen=True)
class Scenario:
    scenario_id: int
    price_multiplier: float
    vol_direction: float
    pl_weight: float


SCENARIOS = (
    Scenario(1, 0.0, 1.0, 1.0),
    Scenario(2, 0.0, -1.0, 1.0),
    Scenario(3, 1.0 / 3.0, 1.0, 1.0),
    Scenario(4, 1.0 / 3.0, -1.0, 1.0),
    Scenario(5, -1.0 / 3.0, 1.0, 1.0),
    Scenario(6, -1.0 / 3.0, -1.0, 1.0),
    Scenario(7, 2.0 / 3.0, 1.0, 1.0),
    Scenario(8, 2.0 / 3.0, -1.0, 1.0),
    Scenario(9, -2.0 / 3.0, 1.0, 1.0),
    Scenario(10, -2.0 / 3.0, -1.0, 1.0),
    Scenario(11, 1.0, 1.0, 1.0),
    Scenario(12, 1.0, -1.0, 1.0),
    Scenario(13, -1.0, 1.0, 1.0),
    Scenario(14, -1.0, -1.0, 1.0),
    Scenario(15, 3.0, 1.0, 0.28),
    Scenario(16, -3.0, -1.0, 0.28),
)

_FUTURES_SUFFIX = re.compile(r"^(\d{4})-(\d{2})$")
_OPTION_SUFFIX = re.compile(r"^(\d{4})-(\d{2})-([CP])-(\d+\.\d{2})$")


@dataclass(frozen=True)
class Instrument:
    instrument_id: str
    product: str
    month: str
    underlying_id: str
    option_kind: str | None
    strike: float | None

    @property
    def is_option(self) -> bool:
        return self.option_kind is not None


@dataclass(frozen=True)
class PositionState:
    instrument: Instrument
    qty: float
    product_config: dict[str, Any]
    atm_value: float
    atm_delta: float
    scenario_pl: tuple[Decimal, ...]
    scenario_delta: tuple[float, ...]


@dataclass(frozen=True)
class CCState:
    cc_id: str
    currency: str
    ics_group: str | None
    positions: tuple[PositionState, ...]
    scenario_pl: tuple[Decimal, ...]
    scanning_risk: Decimal
    worst_scenario_id: int
    intra_charge: Decimal
    outright_delta: float
    som: Decimal
    nov_credit: Decimal


def q2(value: Decimal) -> Decimal:
    """Round a decimal monetary amount to cents, half to even."""

    rounded = value.quantize(CENT, rounding=ROUND_HALF_EVEN)
    return Decimal("0.00") if rounded == 0 else rounded


def _decimal_from_float(value: float) -> Decimal:
    """Use the binary64 value's shortest round-trippable decimal spelling."""

    return Decimal(str(float(value)))


def _rounded_float_money(value: float) -> Decimal:
    return q2(_decimal_from_float(value))


def scenario_money(value: float) -> Decimal:
    """Apply the special conversion required for position-scenario P/L."""

    return q2(Decimal(format(float(value), ".10f")))


def net_positions(portfolio: dict[str, Any]) -> dict[str, float]:
    """Net duplicate instrument rows before parsing or valuing instruments."""

    quantities: dict[str, list[float]] = defaultdict(list)
    for row in portfolio["positions"]:
        quantities[row["instrument_id"]].append(float(row["qty"]))
    netted = {
        instrument_id: math.fsum(parts)
        for instrument_id, parts in quantities.items()
    }
    return {instrument_id: qty for instrument_id, qty in netted.items() if qty != 0.0}


def _parse_instrument(instrument_id: str, product_names: list[str]) -> Instrument:
    # Matching configured product names, longest first, permits product names
    # containing '-' without making the instrument grammar ambiguous.
    for product in product_names:
        prefix = product + "-"
        if not instrument_id.startswith(prefix):
            continue
        suffix = instrument_id[len(prefix) :]
        option_match = _OPTION_SUFFIX.fullmatch(suffix)
        if option_match is not None:
            year, month_number, kind, strike_text = option_match.groups()
            date(int(year), int(month_number), 1)  # validate the month
            month = f"{year}-{month_number}"
            return Instrument(
                instrument_id=instrument_id,
                product=product,
                month=month,
                underlying_id=f"{product}-{month}",
                option_kind=kind,
                strike=float(strike_text),
            )
        futures_match = _FUTURES_SUFFIX.fullmatch(suffix)
        if futures_match is not None:
            year, month_number = futures_match.groups()
            date(int(year), int(month_number), 1)  # validate the month
            month = f"{year}-{month_number}"
            return Instrument(
                instrument_id=instrument_id,
                product=product,
                month=month,
                underlying_id=instrument_id,
                option_kind=None,
                strike=None,
            )
    raise ValueError(f"invalid or unconfigured instrument_id: {instrument_id!r}")


def product_of(instrument_id: str) -> str:
    """Return the product for conventional (non-hyphenated product) ids.

    Kept as a compatibility helper; the engine itself uses
    :func:`_parse_instrument`, which also supports configured product names that
    contain hyphens.
    """

    return instrument_id.split("-", 1)[0]


def is_option(instrument_id: str) -> bool:
    return re.search(r"-\d{4}-\d{2}-[CP]-\d+\.\d{2}$", instrument_id) is not None


def _position_state(
    instrument: Instrument,
    qty: float,
    product_config: dict[str, Any],
    market: dict[str, Any],
    valuation_date: date,
) -> PositionState:
    forward = float(market["futures_price"][instrument.underlying_id])
    scan_range = float(product_config["price_scan_range"])
    vol_scan_fraction = float(product_config["vol_scan_fraction"])
    multiplier = float(product_config["multiplier"])

    if instrument.is_option:
        assert instrument.strike is not None
        assert instrument.option_kind is not None
        strike = instrument.strike
        vol = float(market["atm_vol"][instrument.instrument_id])
        expiry = date.fromisoformat(market["option_expiry"][instrument.instrument_id])
        time_to_expiry = year_fraction(valuation_date, expiry)
        call = instrument.option_kind == "C"
        atm_value = black_price(forward, strike, vol, time_to_expiry, call)
        atm_delta = black_delta(forward, strike, vol, time_to_expiry, call)
    else:
        strike = 0.0
        vol = 0.0
        time_to_expiry = 0.0
        call = False
        atm_value = 0.0
        atm_delta = 1.0

    position_pl: list[Decimal] = []
    position_delta: list[float] = []
    for scenario in SCENARIOS:
        shocked_forward_unfloored = forward + scenario.price_multiplier * scan_range
        if instrument.is_option:
            # The methodology explicitly floors shocked inputs before Black-76.
            shocked_forward = max(shocked_forward_unfloored, 1e-8)
            shocked_vol = max(
                vol * (1.0 + scenario.vol_direction * vol_scan_fraction),
                1e-6,
            )
            shocked_value = black_price(
                shocked_forward,
                strike,
                shocked_vol,
                time_to_expiry,
                call,
            )
            raw_pl = qty * (shocked_value - atm_value) * multiplier
            per_contract_delta = black_delta(
                shocked_forward,
                strike,
                shocked_vol,
                time_to_expiry,
                call,
            )
        else:
            # Use F' - F literally: its binary64 cancellation is part of the
            # specified position-scenario P/L before decimal conversion.
            raw_pl = qty * (shocked_forward_unfloored - forward) * multiplier
            per_contract_delta = 1.0
        position_pl.append(scenario_money(raw_pl * scenario.pl_weight))
        position_delta.append(per_contract_delta)

    return PositionState(
        instrument=instrument,
        qty=qty,
        product_config=product_config,
        atm_value=atm_value,
        atm_delta=atm_delta,
        scenario_pl=tuple(position_pl),
        scenario_delta=tuple(position_delta),
    )


def _scenario_totals(positions: list[PositionState]) -> tuple[Decimal, ...]:
    return tuple(
        sum((position.scenario_pl[index] for position in positions), Decimal("0.00"))
        for index in range(len(SCENARIOS))
    )


def _worst_scenario(scenario_pl: tuple[Decimal, ...]) -> tuple[int, Decimal]:
    index = min(range(len(SCENARIOS)), key=lambda i: (scenario_pl[i], SCENARIOS[i].scenario_id))
    return SCENARIOS[index].scenario_id, scenario_pl[index]


def _composite_bucket_deltas(
    positions: list[PositionState],
    scenario_pl: tuple[Decimal, ...],
    worst_scenario_id: int,
) -> dict[str, float]:
    if worst_scenario_id <= 14:
        worst_index = worst_scenario_id - 1
        next_index = min(
            (index for index in range(14) if index != worst_index),
            key=lambda index: (scenario_pl[index], SCENARIOS[index].scenario_id),
        )
        scenario_indexes = (worst_index, next_index)
    else:
        scenario_indexes = (worst_scenario_id - 1,)

    by_bucket: dict[str, list[float]] = defaultdict(list)
    for position in positions:
        if len(scenario_indexes) == 2:
            per_contract_delta = (
                position.scenario_delta[scenario_indexes[0]]
                + position.scenario_delta[scenario_indexes[1]]
            ) / 2.0
        else:
            per_contract_delta = position.scenario_delta[scenario_indexes[0]]
        by_bucket[position.instrument.month].append(position.qty * per_contract_delta)
    return {bucket: math.fsum(deltas) for bucket, deltas in by_bucket.items()}


def _month_start(month: str) -> date:
    return date(int(month[:4]), int(month[5:7]), 1)


def _reduce_toward_zero(value: float, amount: float) -> float:
    residual = max(0.0, abs(value) - amount)
    if residual == 0.0:
        return 0.0
    return math.copysign(residual, value)


def _intra_spread(
    bucket_deltas: dict[str, float],
    tiers: dict[str, Any],
) -> tuple[Decimal, float]:
    remaining = dict(bucket_deltas)
    charge_parts: list[float] = []

    while True:
        nonzero = [bucket for bucket, delta in remaining.items() if delta != 0.0]
        if not nonzero:
            break
        bucket_a = min(nonzero, key=lambda bucket: (-abs(remaining[bucket]), bucket))
        delta_a = remaining[bucket_a]
        opposite = [
            bucket
            for bucket in nonzero
            if (delta_a > 0.0 and remaining[bucket] < 0.0)
            or (delta_a < 0.0 and remaining[bucket] > 0.0)
        ]
        if not opposite:
            break

        start_a = _month_start(bucket_a)
        bucket_b = min(
            opposite,
            key=lambda bucket: (
                abs((_month_start(bucket) - start_a).days),
                -abs(remaining[bucket]),
                bucket,
            ),
        )
        matched = min(abs(delta_a), abs(remaining[bucket_b]))
        remaining[bucket_a] = _reduce_toward_zero(delta_a, matched)
        remaining[bucket_b] = _reduce_toward_zero(remaining[bucket_b], matched)

        day_distance = abs((_month_start(bucket_b) - start_a).days)
        if day_distance == 0:
            # Buckets are normally unique YYYY-MM values, but retain the
            # methodology's explicit same-month no-charge behavior.
            continue
        if day_distance <= 32:
            rate = float(tiers["adjacent"])
        elif day_distance <= 125:
            rate = float(tiers["mid"])
        else:
            rate = float(tiers["back"])
        charge_parts.append(matched * rate * math.sqrt(day_distance / 365.0))

    charge = _rounded_float_money(math.fsum(charge_parts))
    outright_delta = math.fsum(remaining.values())
    return charge, outright_delta


def _short_option_minimum(positions: list[PositionState]) -> Decimal:
    contributions = [
        float(position.product_config["som_rate"])
        * abs(position.qty)
        * (1.0 + max(0.0, 0.25 - abs(position.atm_delta)))
        for position in positions
        if position.instrument.is_option and position.qty < 0.0
    ]
    return _rounded_float_money(math.fsum(contributions))


def _nov_credit(positions: list[PositionState]) -> Decimal:
    contributions = [
        max(
            0.0,
            position.qty
            * position.atm_value
            * float(position.product_config["multiplier"]),
        )
        for position in positions
        if position.instrument.is_option
        and position.qty > 0.0
        and abs(position.atm_delta) < 0.35
    ]
    return _rounded_float_money(math.fsum(contributions))


def _cc_state(cc_id: str, positions: list[PositionState]) -> CCState:
    currencies = {position.product_config["currency"] for position in positions}
    if len(currencies) != 1:
        raise ValueError(f"combined commodity {cc_id!r} has multiple currencies")
    currency = next(iter(currencies))

    groups = {position.product_config["ics_group"] for position in positions}
    ics_group = next(iter(groups)) if len(groups) == 1 else None

    tier_values = {
        (
            float(position.product_config["intra_tiers"]["adjacent"]),
            float(position.product_config["intra_tiers"]["mid"]),
            float(position.product_config["intra_tiers"]["back"]),
        )
        for position in positions
    }
    if len(tier_values) != 1:
        raise ValueError(f"combined commodity {cc_id!r} has multiple intra tier tables")
    adjacent, mid, back = next(iter(tier_values))
    tiers = {"adjacent": adjacent, "mid": mid, "back": back}

    scenario_pl = _scenario_totals(positions)
    worst_scenario_id, worst_pl = _worst_scenario(scenario_pl)
    scanning_risk = max(Decimal("0.00"), -worst_pl)
    bucket_deltas = _composite_bucket_deltas(positions, scenario_pl, worst_scenario_id)
    intra_charge, outright_delta = _intra_spread(bucket_deltas, tiers)

    return CCState(
        cc_id=cc_id,
        currency=currency,
        ics_group=ics_group,
        positions=tuple(positions),
        scenario_pl=scenario_pl,
        scanning_risk=scanning_risk,
        worst_scenario_id=worst_scenario_id,
        intra_charge=intra_charge,
        outright_delta=outright_delta,
        som=_short_option_minimum(positions),
        nov_credit=_nov_credit(positions),
    )


def _inter_commodity_credits(
    cc_states: dict[str, CCState],
    inter_spreads: list[dict[str, Any]],
) -> dict[str, Decimal]:
    residual = {cc_id: state.outright_delta for cc_id, state in cc_states.items()}
    credits = {cc_id: Decimal("0") for cc_id in cc_states}

    for spread in sorted(inter_spreads, key=lambda item: int(item["priority"])):
        leg_a = spread["leg_a"]
        leg_b = spread["leg_b"]
        state_a = cc_states.get(leg_a)
        state_b = cc_states.get(leg_b)
        if state_a is None or state_b is None:
            continue
        if (
            state_a.ics_group is None
            or state_a.ics_group != state_b.ics_group
            or state_a.ics_group != spread["ics_group"]
            or state_a.currency != state_b.currency
        ):
            continue

        delta_a = residual[leg_a]
        delta_b = residual[leg_b]
        if delta_a == 0.0 or delta_b == 0.0:
            continue
        if not ((delta_a > 0.0 and delta_b < 0.0) or (delta_a < 0.0 and delta_b > 0.0)):
            continue

        ratio_a = float(spread["ratio_a"])
        ratio_b = float(spread["ratio_b"])
        if ratio_a <= 0.0 or ratio_b <= 0.0:
            raise ValueError("inter-commodity spread ratios must be positive")
        units_a = delta_a / ratio_a
        units_b = delta_b / ratio_b
        if not ((units_a > 0.0 and units_b < 0.0) or (units_a < 0.0 and units_b > 0.0)):
            continue

        paired_units = min(abs(units_a), abs(units_b))
        credit = _decimal_from_float(paired_units * float(spread["credit_per_unit"]))
        credit_b = q2(credit / Decimal(2))
        credit_a = credit - credit_b
        credits[leg_a] += credit_a
        credits[leg_b] += credit_b

        residual[leg_a] = _reduce_toward_zero(delta_a, paired_units * ratio_a)
        residual[leg_b] = _reduce_toward_zero(delta_b, paired_units * ratio_b)

    return credits


def compute_report(
    portfolio: dict[str, Any],
    market: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    net = net_positions(portfolio)
    products = config["products"]
    product_names = sorted(products, key=lambda name: (-len(name), name))
    valuation_date = date.fromisoformat(market["valuation_date"])

    by_cc: dict[str, list[PositionState]] = defaultdict(list)
    for instrument_id, qty in net.items():
        instrument = _parse_instrument(instrument_id, product_names)
        product_config = products[instrument.product]
        state = _position_state(instrument, qty, product_config, market, valuation_date)
        by_cc[product_config["cc_id"]].append(state)

    cc_states = {cc_id: _cc_state(cc_id, positions) for cc_id, positions in by_cc.items()}
    inter_credits = _inter_commodity_credits(cc_states, config["inter_spreads"])
    fx = {currency: Decimal(str(value)) for currency, value in market["fx_to_usd"].items()}

    rows: list[dict[str, Any]] = []
    total_margin_usd = Decimal("0.00")
    for cc_id in sorted(cc_states):
        state = cc_states[cc_id]
        exact_inter_credit = inter_credits[cc_id]
        raw_margin = q2(
            state.scanning_risk
            + state.intra_charge
            - exact_inter_credit
            - state.nov_credit
        )
        cc_margin_native = max(raw_margin, state.som)
        cc_margin_usd = q2(cc_margin_native * fx[state.currency])
        total_margin_usd += cc_margin_usd
        rows.append(
            {
                "cc_id": cc_id,
                "currency": state.currency,
                "scanning_risk": q2(state.scanning_risk),
                "intra_charge": state.intra_charge,
                # C_A deliberately retains the residual of the split for the
                # raw calculation; report money is displayed to cents.
                "inter_credit": q2(exact_inter_credit),
                "nov_credit": state.nov_credit,
                "som": state.som,
                "raw_margin": raw_margin,
                "cc_margin_native": cc_margin_native,
                "cc_margin_usd": cc_margin_usd,
                "worst_scenario_id": state.worst_scenario_id,
            }
        )

    return {
        "valuation_date": market["valuation_date"],
        "currency": "USD",
        "total_margin_usd": total_margin_usd,
        "combined_commodities": rows,
    }


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def _json_text(value: Any, indent: int = 0) -> str:
    """Encode the fixed report shape while preserving two-place JSON numbers."""

    if isinstance(value, Decimal):
        return format(q2(value), ".2f")
    if isinstance(value, dict):
        if not value:
            return "{}"
        inner = []
        for key, item in value.items():
            inner.append(
                " " * (indent + 2)
                + json.dumps(key)
                + ": "
                + _json_text(item, indent + 2)
            )
        return "{\n" + ",\n".join(inner) + "\n" + " " * indent + "}"
    if isinstance(value, list):
        if not value:
            return "[]"
        inner = [" " * (indent + 2) + _json_text(item, indent + 2) for item in value]
        return "[\n" + ",\n".join(inner) + "\n" + " " * indent + "]"
    return json.dumps(value, allow_nan=False)


def write_report(report: dict[str, Any], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_json_text(report) + "\n")
