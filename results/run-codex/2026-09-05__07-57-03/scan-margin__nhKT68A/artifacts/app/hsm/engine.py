"""House Scan Margin calculation engine."""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_CEILING, ROUND_HALF_EVEN, Decimal
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from typing import Any

try:  # Package import (tests and library use).
    from .lib.black76 import delta as black_delta
    from .lib.black76 import price as black_price
    from .lib.black76 import year_fraction
except ImportError:  # Script import through run_margin.py.
    from lib.black76 import delta as black_delta
    from lib.black76 import price as black_price
    from lib.black76 import year_fraction


CENT = Decimal("0.01")
ZERO = Decimal("0.00")

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
VOL_UP = tuple(index % 2 == 0 for index in range(16))
PL_WEIGHT = (1.0,) * 14 + (0.28, 0.28)

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


def _decimal(value: Any) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def q2(value: Decimal | int | float) -> Decimal:
    rounded = _decimal(value).quantize(CENT, rounding=ROUND_HALF_EVEN)
    return ZERO if rounded == 0 else rounded


def scenario_money(value: float) -> Decimal:
    """Apply the methodology's binary64 -> 10dp -> cent conversion."""

    return q2(Decimal(format(float(value), ".10f")))


def _sum_money_terms(terms) -> Decimal:
    return q2(sum((_decimal(term) for term in terms), Decimal(0)))


def net_positions(portfolio: dict) -> dict[str, Decimal]:
    quantities: dict[str, Decimal] = defaultdict(Decimal)
    for row in portfolio["positions"]:
        quantities[row["instrument_id"]] += _decimal(row["qty"])
    return {iid: qty for iid, qty in quantities.items() if qty != 0}


@dataclass(frozen=True)
class Instrument:
    iid: str
    product: str
    bucket: str
    is_option: bool
    is_call: bool = False
    strike: float = 0.0


def _parse_instrument(iid: str) -> Instrument:
    parts = iid.split("-")
    if len(parts) == 3:
        product, year_text, month_text = parts
        is_option = False
        is_call = False
        strike = 0.0
    elif len(parts) == 5 and parts[3] in ("C", "P"):
        product, year_text, month_text, cp, strike_text = parts
        is_option = True
        is_call = cp == "C"
        strike = float(strike_text)
    else:
        raise ValueError(f"invalid instrument_id: {iid}")
    year, month = int(year_text), int(month_text)
    # Constructing a date validates both the year and month.
    date(year, month, 1)
    return Instrument(
        iid=iid,
        product=product,
        bucket=f"{year:04d}-{month:02d}",
        is_option=is_option,
        is_call=is_call,
        strike=strike,
    )


def _delivery_scale(bucket: str, valuation: date, house: dict) -> float:
    year, month = (int(part) for part in bucket.split("-"))
    days = (date(year, month, 1) - valuation).days
    if days <= int(house["delivery_scale_days"]):
        return 1.0
    return max(math.sqrt(days / 365.0), float(house["delivery_scale_floor"]))


def _shocked_forward(forward: float, multiple: float, psr: float, mode: str) -> float:
    if mode == "linear":
        shocked = forward + multiple * psr
    elif mode == "log":
        shocked = forward * math.exp(multiple * psr / forward) if forward > 0 else 1e-8
    else:
        raise ValueError(f"unknown shock_mode: {mode}")
    return max(shocked, 1e-8)


@dataclass
class PositionCalc:
    instrument: Instrument
    qty: Decimal
    cc_id: str
    currency: str
    product_config: dict
    scenario_pl: tuple[Decimal, ...]
    scenario_delta: tuple[float, ...]
    atm_delta: float
    unshocked_value: float


def _calculate_position(
    instrument: Instrument,
    qty: Decimal,
    market: dict,
    product_config: dict,
    valuation: date,
    house: dict,
) -> PositionCalc:
    underlying = f"{instrument.product}-{instrument.bucket}"
    forward = float(market["futures_price"][underlying])
    multiplier = float(product_config["multiplier"])
    psr = float(product_config["price_scan_range"]) * _delivery_scale(
        instrument.bucket, valuation, house
    )
    qty_float = float(qty)

    if instrument.is_option:
        vol = float(market["atm_vol"][instrument.iid])
        expiry = date.fromisoformat(market["option_expiry"][instrument.iid])
        t = year_fraction(valuation, expiry)
        unshocked = black_price(forward, instrument.strike, vol, t, instrument.is_call)
        atm_delta = black_delta(forward, instrument.strike, vol, t, instrument.is_call)
    else:
        vol = 0.0
        t = 0.0
        unshocked = 0.0
        atm_delta = 1.0

    scenario_pl: list[Decimal] = []
    scenario_delta: list[float] = []
    for index, multiple in enumerate(PRICE_MULT):
        shocked_forward = _shocked_forward(
            forward, multiple, psr, product_config["shock_mode"]
        )
        weight = PL_WEIGHT[index]
        if instrument.is_option:
            fraction = (
                float(product_config["vol_scan_fraction"])
                if VOL_UP[index]
                else -float(product_config["vsf_down"])
            )
            shocked_vol = max(vol * (1.0 + fraction), 1e-6)
            shocked_value = black_price(
                shocked_forward, instrument.strike, shocked_vol, t, instrument.is_call
            )
            raw_pl = qty_float * (shocked_value - unshocked) * multiplier * weight
            per_contract_delta = black_delta(
                shocked_forward, instrument.strike, shocked_vol, t, instrument.is_call
            )
        else:
            raw_pl = qty_float * (shocked_forward - forward) * multiplier * weight
            per_contract_delta = 1.0
        scenario_pl.append(scenario_money(raw_pl))
        scenario_delta.append(per_contract_delta)

    return PositionCalc(
        instrument=instrument,
        qty=qty,
        cc_id=product_config["cc_id"],
        currency=product_config["currency"],
        product_config=product_config,
        scenario_pl=tuple(scenario_pl),
        scenario_delta=tuple(scenario_delta),
        atm_delta=atm_delta,
        unshocked_value=unshocked,
    )


def _bucket_date(bucket: str) -> date:
    year, month = (int(part) for part in bucket.split("-"))
    return date(year, month, 1)


def _intra_spread(
    bucket_delta: dict[str, float], product_config: dict
) -> tuple[Decimal, dict[str, float]]:
    remaining = dict(bucket_delta)
    charge_terms: list[Decimal] = []

    while True:
        active = [(bucket, value) for bucket, value in remaining.items() if value != 0.0]
        if not active:
            break
        bucket_a, delta_a = min(active, key=lambda item: (-abs(item[1]), item[0]))
        opposites = [item for item in active if item[1] * delta_a < 0.0]
        if not opposites:
            break
        date_a = _bucket_date(bucket_a)
        bucket_b, delta_b = min(
            opposites,
            key=lambda item: (
                abs((_bucket_date(item[0]) - date_a).days),
                -abs(item[1]),
                item[0],
            ),
        )
        matched = min(abs(delta_a), abs(delta_b))
        days = abs((_bucket_date(bucket_b) - date_a).days)
        tiers = product_config["intra_tiers"]
        if days <= 32:
            rate = _decimal(tiers["adjacent"])
        elif days <= 125:
            rate = _decimal(tiers["mid"])
        else:
            rate = _decimal(tiers["back"])
        charge_terms.append(
            _decimal(matched) * rate * _decimal(math.sqrt(days / 365.0))
        )

        abs_a, abs_b = abs(delta_a), abs(delta_b)
        remaining[bucket_a] = (
            0.0 if abs_a <= matched else math.copysign(abs_a - matched, delta_a)
        )
        remaining[bucket_b] = (
            0.0 if abs_b <= matched else math.copysign(abs_b - matched, delta_b)
        )

    return _sum_money_terms(charge_terms), remaining


def _month_number(bucket: str) -> int:
    year, month = (int(part) for part in bucket.split("-"))
    return year * 12 + month


def _strip_credit(remaining: dict[str, float], rate_value: Any) -> Decimal:
    rate = _decimal(rate_value)
    if rate == 0:
        return ZERO
    months = sorted(bucket for bucket, value in remaining.items() if value != 0.0)
    if not months:
        return ZERO

    runs: list[list[str]] = []
    run = [months[0]]
    for bucket in months[1:]:
        if _month_number(bucket) == _month_number(run[-1]) + 1:
            run.append(bucket)
        else:
            runs.append(run)
            run = [bucket]
    runs.append(run)

    terms = []
    for current in runs:
        if len(current) >= 3:
            minimum = min(abs(remaining[bucket]) for bucket in current)
            terms.append(Decimal(len(current) - 2) * rate * _decimal(minimum))
    return _sum_money_terms(terms)


def _som(positions: list[PositionCalc]) -> Decimal:
    terms = []
    for position in positions:
        if not position.instrument.is_option or position.qty >= 0:
            continue
        uplift = 1.0 + max(0.0, 0.25 - abs(position.atm_delta))
        terms.append(
            _decimal(position.product_config["som_rate"])
            * abs(position.qty)
            * _decimal(uplift)
        )
    return _sum_money_terms(terms)


def _nov(positions: list[PositionCalc], scanning_risk: Decimal) -> Decimal:
    terms = []
    for position in positions:
        if (
            position.instrument.is_option
            and position.qty > 0
            and abs(position.atm_delta) < 0.35
        ):
            value = (
                float(position.qty)
                * position.unshocked_value
                * float(position.product_config["multiplier"])
            )
            terms.append(_decimal(max(0.0, value)))
    uncapped = _sum_money_terms(terms)
    return q2(min(uncapped, scanning_risk))


def _liquidity_addon(positions: list[PositionCalc]) -> Decimal:
    terms = []
    for position in positions:
        if not position.instrument.is_option or position.qty >= 0:
            continue
        cutoff = float(position.product_config["lao_otm"])
        factor = max(0.0, cutoff - abs(position.atm_delta))
        terms.append(
            _decimal(position.product_config["lao_rate"])
            * abs(position.qty)
            * _decimal(factor)
        )
    return _sum_money_terms(terms)


@dataclass
class CCState:
    cc_id: str
    currency: str
    ics_group: str
    product_config: dict
    positions: list[PositionCalc]
    scanning_risk: Decimal
    worst_scenario_id: int
    intra_charge: Decimal
    strip_credit: Decimal
    som: Decimal
    nov_credit: Decimal
    outright_delta: float
    residual_delta: float = 0.0
    inter_credit: Decimal = ZERO


@dataclass(frozen=True)
class AdmissibleSpread:
    config_index: int
    priority: int
    legs: tuple[tuple[str, int], ...]
    credit_rate: Decimal


def _cc_metadata(products: dict) -> dict[str, tuple[str, str]]:
    metadata: dict[str, tuple[str, str]] = {}
    for product in products.values():
        cc_id = product["cc_id"]
        value = (product["ics_group"], product["currency"])
        if cc_id in metadata and metadata[cc_id] != value:
            raise ValueError(f"inconsistent ICS group or currency for CC {cc_id}")
        metadata[cc_id] = value
    return metadata


def _admissible_spreads(
    spread_rows: list[dict],
    outright: dict[str, float],
    metadata: dict[str, tuple[str, str]],
) -> list[AdmissibleSpread]:
    result = []
    for index, row in enumerate(spread_rows):
        legs = row["legs"]
        base_legs = [leg for leg in legs if leg["role"] == "base"]
        opp_legs = [leg for leg in legs if leg["role"] == "opp"]
        if len(base_legs) != 1 or not opp_legs:
            continue
        if any(
            leg["cc"] not in outright
            or outright[leg["cc"]] == 0.0
            or leg["cc"] not in metadata
            or int(leg["ratio"]) <= 0
            for leg in legs
        ):
            continue
        groups = {metadata[leg["cc"]][0] for leg in legs}
        currencies = {metadata[leg["cc"]][1] for leg in legs}
        if groups != {row["ics_group"]} or len(currencies) != 1:
            continue
        base_sign = math.copysign(1.0, outright[base_legs[0]["cc"]])
        if any(math.copysign(1.0, outright[leg["cc"]]) == base_sign for leg in opp_legs):
            continue

        # Aggregate duplicate CC legs so the shared-resource constraint remains
        # correct even if a template happens to name a CC more than once.
        leg_ratios: dict[str, int] = defaultdict(int)
        for leg in legs:
            leg_ratios[leg["cc"]] += int(leg["ratio"])
        rate = _decimal(row["credit_per_unit"]) * (
            Decimal(1) - _decimal(row["rho"])
        )
        result.append(
            AdmissibleSpread(
                config_index=index,
                priority=int(row["priority"]),
                legs=tuple(leg_ratios.items()),
                credit_rate=rate,
            )
        )
    return result


def _optimize_spreads(
    spreads: list[AdmissibleSpread], outright: dict[str, float]
) -> tuple[list[int], dict[str, int]]:
    """Return exact credit-maximizing integer units and CC consumption."""

    if not spreads:
        return [], {}
    ccs = sorted({cc for spread in spreads for cc, _ in spread.legs})
    cc_index = {cc: index for index, cc in enumerate(ccs)}
    capacities = tuple(int(math.floor(abs(outright[cc]))) for cc in ccs)

    def max_units(spread_index: int, remaining: tuple[int, ...]) -> int:
        return min(
            remaining[cc_index[cc]] // ratio
            for cc, ratio in spreads[spread_index].legs
        )

    @lru_cache(maxsize=None)
    def credit_cents(spread_index: int, units: int) -> int:
        return int(q2(Decimal(units) * spreads[spread_index].credit_rate) * 100)

    # Search valuable, resource-efficient templates first to establish a strong
    # incumbent quickly. Result tie-breaking still uses original config order.
    search_order = sorted(
        range(len(spreads)),
        key=lambda index: (
            spreads[index].credit_rate
            / Decimal(sum(ratio for _cc, ratio in spreads[index].legs)),
            spreads[index].credit_rate,
            -spreads[index].config_index,
        ),
        reverse=True,
    )

    # A row's rounded credit is never greater than units times the ceiling of
    # its unrounded per-unit credit in cents. This gives a rigorous linear bound.
    per_unit_bounds = [
        max(
            0,
            int(
                (spread.credit_rate * 100).to_integral_value(
                    rounding=ROUND_CEILING
                )
            ),
        )
        for spread in spreads
    ]

    def remaining_credit_bound(depth: int, remaining: tuple[int, ...]) -> int:
        indices = search_order[depth:]
        if not indices:
            return 0

        # Ignoring shared capacities is one valid upper bound.
        independent = sum(
            max(0, credit_cents(index, max_units(index, remaining)))
            for index in indices
        )

        # Assign each row's entire value to one of the resources it consumes.
        # Capacity times the greatest assigned value density is then a valid
        # dual bound. Choosing the tightest leg keeps that bound useful.
        density_by_cc: dict[str, Fraction] = {}
        for index in indices:
            if per_unit_bounds[index] == 0:
                continue
            spread = spreads[index]
            cc, ratio = min(
                spread.legs,
                key=lambda leg: (
                    Fraction(remaining[cc_index[leg[0]]], leg[1]),
                    leg[0],
                ),
            )
            density = Fraction(per_unit_bounds[index], ratio)
            density_by_cc[cc] = max(density_by_cc.get(cc, Fraction(0)), density)
        resource = sum(
            remaining[cc_index[cc]] * density
            for cc, density in density_by_cc.items()
        )
        resource_floor = resource.numerator // resource.denominator
        return min(independent, resource_floor)

    current = [0] * len(spreads)
    best_credit = -1
    best_counts: tuple[int, ...] | None = None

    def lexicographic_upper(depth: int, remaining: tuple[int, ...]) -> tuple[int, ...]:
        upper = current.copy()
        for index in search_order[depth:]:
            upper[index] = max_units(index, remaining)
        return tuple(upper)

    def search(depth: int, remaining: tuple[int, ...], total_credit: int) -> None:
        nonlocal best_credit, best_counts
        bound = remaining_credit_bound(depth, remaining)
        possible = total_credit + bound
        if possible < best_credit:
            return
        if (
            possible == best_credit
            and best_counts is not None
            and lexicographic_upper(depth, remaining) <= best_counts
        ):
            return
        if depth == len(search_order):
            candidate = tuple(current)
            if total_credit > best_credit or (
                total_credit == best_credit
                and (best_counts is None or candidate > best_counts)
            ):
                best_credit = total_credit
                best_counts = candidate
            return

        index = search_order[depth]
        spread = spreads[index]
        maximum = max_units(index, remaining)
        for units in range(maximum, -1, -1):
            next_remaining = list(remaining)
            for cc, ratio in spread.legs:
                next_remaining[cc_index[cc]] -= units * ratio
            current[index] = units
            search(
                depth + 1,
                tuple(next_remaining),
                total_credit + credit_cents(index, units),
            )
        current[index] = 0

    search(0, capacities, 0)
    assert best_counts is not None
    optimized = best_counts
    consumption: dict[str, int] = defaultdict(int)
    for spread, units in zip(spreads, optimized):
        for cc, ratio in spread.legs:
            consumption[cc] += units * ratio
    return list(optimized), dict(consumption)


def _apply_inter_spreads(
    states: dict[str, CCState], spread_rows: list[dict], metadata: dict[str, tuple[str, str]]
) -> None:
    outright = {cc: state.outright_delta for cc, state in states.items()}
    spreads = _admissible_spreads(spread_rows, outright, metadata)
    units, consumption = _optimize_spreads(spreads, outright)

    credits: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for spread, count in zip(spreads, units):
        if count == 0:
            continue
        total_credit = q2(Decimal(count) * spread.credit_rate)
        original_legs = spread_rows[spread.config_index]["legs"]
        count_legs = len(original_legs)
        even_share = q2(total_credit / Decimal(count_legs))
        for leg in original_legs[:-1]:
            credits[leg["cc"]] += even_share
        credits[original_legs[-1]["cc"]] += total_credit - even_share * (
            count_legs - 1
        )

    for cc, state in states.items():
        state.inter_credit = q2(credits[cc])
        used = consumption.get(cc, 0)
        residual_abs = max(0.0, abs(state.outright_delta) - used)
        state.residual_delta = (
            0.0
            if residual_abs == 0.0
            else math.copysign(residual_abs, state.outright_delta)
        )


def _build_cc_state(cc_id: str, positions: list[PositionCalc]) -> CCState:
    currencies = {position.currency for position in positions}
    groups = {position.product_config["ics_group"] for position in positions}
    if len(currencies) != 1 or len(groups) != 1:
        raise ValueError(f"inconsistent currency or ICS group inside CC {cc_id}")
    product_config = positions[0].product_config

    cc_pl = [
        sum((position.scenario_pl[index] for position in positions), Decimal(0))
        for index in range(16)
    ]
    worst_index = min(range(16), key=lambda index: (cc_pl[index], index))
    scanning_risk = q2(max(Decimal(0), -cc_pl[worst_index]))
    if worst_index < 14:
        next_index = min(
            (index for index in range(14) if index != worst_index),
            key=lambda index: (cc_pl[index], index),
        )
    else:
        next_index = None

    bucket_delta: dict[str, float] = defaultdict(float)
    for position in positions:
        if next_index is None:
            composite = position.scenario_delta[worst_index]
        else:
            composite = (
                position.scenario_delta[worst_index]
                + position.scenario_delta[next_index]
            ) / 2.0
        bucket_delta[position.instrument.bucket] += composite * float(position.qty)

    intra_charge, remaining = _intra_spread(bucket_delta, product_config)
    strip_credit = _strip_credit(remaining, product_config["strip_rate"])
    outright_delta = sum(remaining.values())
    return CCState(
        cc_id=cc_id,
        currency=next(iter(currencies)),
        ics_group=next(iter(groups)),
        product_config=product_config,
        positions=positions,
        scanning_risk=scanning_risk,
        worst_scenario_id=worst_index + 1,
        intra_charge=intra_charge,
        strip_credit=strip_credit,
        som=_som(positions),
        nov_credit=_nov(positions, scanning_risk),
        outright_delta=outright_delta,
        residual_delta=outright_delta,
    )


def compute_report(portfolio: dict, market: dict, config: dict) -> dict:
    net = net_positions(portfolio)
    products = config["products"]
    valuation = date.fromisoformat(market["valuation_date"])

    by_cc: dict[str, list[PositionCalc]] = defaultdict(list)
    for iid, qty in sorted(net.items()):
        instrument = _parse_instrument(iid)
        product_config = products[instrument.product]
        calculated = _calculate_position(
            instrument,
            qty,
            market,
            product_config,
            valuation,
            config["house"],
        )
        by_cc[calculated.cc_id].append(calculated)

    states = {
        cc_id: _build_cc_state(cc_id, positions)
        for cc_id, positions in by_cc.items()
    }
    _apply_inter_spreads(
        states, config["inter_spreads"], _cc_metadata(products)
    )

    rows = []
    total = ZERO
    for cc_id in sorted(states):
        state = states[cc_id]
        threshold = float(state.product_config["concentration_threshold"])
        excess = max(0.0, abs(state.residual_delta) - threshold)
        concentration = q2(
            _decimal(excess) * _decimal(state.product_config["concentration_rate"])
        )
        raw = q2(
            state.scanning_risk
            + state.intra_charge
            + concentration
            - state.inter_credit
            - state.nov_credit
            - state.strip_credit
        )
        liquidity = _liquidity_addon(state.positions)
        native = q2(max(raw, state.som) + liquidity)
        fx = _decimal(market["fx_to_usd"][state.currency])
        usd = q2(native * fx)
        total += usd
        rows.append(
            {
                "cc_id": cc_id,
                "currency": state.currency,
                "scanning_risk": float(state.scanning_risk),
                "intra_charge": float(state.intra_charge),
                "inter_credit": float(state.inter_credit),
                "nov_credit": float(state.nov_credit),
                "som": float(state.som),
                "strip_credit": float(state.strip_credit),
                "concentration_charge": float(concentration),
                "liquidity_addon": float(liquidity),
                "raw_margin": float(raw),
                "cc_margin_native": float(native),
                "cc_margin_usd": float(usd),
                "worst_scenario_id": state.worst_scenario_id,
            }
        )

    return {
        "valuation_date": market["valuation_date"],
        "currency": "USD",
        "total_margin_usd": float(q2(total)),
        "combined_commodities": rows,
    }


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(), parse_float=Decimal)


def _money_as_json_numbers(value: Any, key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {name: _money_as_json_numbers(item, name) for name, item in value.items()}
    if isinstance(value, list):
        return [_money_as_json_numbers(item) for item in value]
    if key in MONEY_FIELDS:
        return f"__HSM_MONEY_{q2(_decimal(value)):.2f}__"
    return value


def write_report(report: dict, path: str | Path) -> None:
    """Write valid JSON while retaining two decimal places on money numbers."""

    prepared = _money_as_json_numbers(report)
    text = json.dumps(prepared, indent=2)
    # The sentinels originate only from numeric schema fields. Removing their
    # JSON quotes produces number tokens such as 1.50 rather than strings.
    text = re.sub(r'"__HSM_MONEY_(-?\d+\.\d{2})__"', r"\1", text)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text + "\n")
