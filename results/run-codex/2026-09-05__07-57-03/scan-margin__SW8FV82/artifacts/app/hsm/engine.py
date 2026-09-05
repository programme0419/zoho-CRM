"""House Scan Margin calculation engine."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from functools import lru_cache
from fractions import Fraction
import json
import math
import re
from pathlib import Path
from typing import Any

try:  # Support both the CLI's top-level import and ``import hsm.engine``.
    from .lib.black76 import delta as black_delta
    from .lib.black76 import price as black_price
    from .lib.black76 import year_fraction
except ImportError:  # pragma: no cover - this is the run_margin.py path
    from lib.black76 import delta as black_delta
    from lib.black76 import price as black_price
    from lib.black76 import year_fraction


CENT = Decimal("0.01")
PRICE_MULT = (0.0, 0.0, 1 / 3, 1 / 3, -1 / 3, -1 / 3, 2 / 3, 2 / 3,
              -2 / 3, -2 / 3, 1.0, 1.0, -1.0, -1.0, 3.0, -3.0)
VOL_DIRECTION = (1, -1, 1, -1, 1, -1, 1, -1, 1, -1, 1, -1, 1, -1, 1, -1)
PL_WEIGHT = (1.0,) * 14 + (0.28, 0.28)
INSTRUMENT_RE = re.compile(
    r"^(?P<product>[^-]+)-(?P<year>\d{4})-(?P<month>\d{2})"
    r"(?:-(?P<cp>[CP])-(?P<strike>\d+(?:\.\d+)?))?$"
)


def _decimal(value: Any) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def q2(value: Any) -> Decimal:
    return _decimal(value).quantize(CENT, rounding=ROUND_HALF_EVEN)


def scenario_money(value: float) -> Decimal:
    """Apply the methodology's binary64 -> 10dp decimal -> cent rule."""

    return Decimal(format(float(value), ".10f")).quantize(CENT, rounding=ROUND_HALF_EVEN)


def rounded_formula(value: float | Decimal) -> Decimal:
    """Round a formula result to cents with decimal half-even semantics."""

    return q2(value if isinstance(value, Decimal) else Decimal(str(float(value))))


@dataclass(frozen=True)
class Instrument:
    instrument_id: str
    product: str
    year: int
    month: int
    cp: str | None
    strike: float | None

    @property
    def is_option(self) -> bool:
        return self.cp is not None

    @property
    def bucket(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    @property
    def future_id(self) -> str:
        return f"{self.product}-{self.bucket}"


@dataclass
class PositionCalc:
    instrument: Instrument
    qty: float
    product_config: dict[str, Any]
    scenario_pl: list[Decimal]
    scenario_delta: list[float]
    atm_delta: float
    option_value: float


@dataclass
class CommodityCalc:
    cc_id: str
    config: dict[str, Any]
    currency: str
    ics_group: str
    positions: list[PositionCalc]
    scenario_pl: list[Decimal]
    worst_scenario_id: int = 1
    scanning_risk: Decimal = Decimal("0.00")
    intra_charge: Decimal = Decimal("0.00")
    strip_credit: Decimal = Decimal("0.00")
    outright_delta: float = 0.0
    residual_delta: float = 0.0
    inter_credit: Decimal = Decimal("0.00")
    nov_credit: Decimal = Decimal("0.00")
    som: Decimal = Decimal("0.00")
    concentration_charge: Decimal = Decimal("0.00")
    liquidity_addon: Decimal = Decimal("0.00")


def _parse_instrument(instrument_id: str) -> Instrument:
    match = INSTRUMENT_RE.fullmatch(instrument_id)
    if match is None:
        raise ValueError(f"invalid instrument_id: {instrument_id}")
    month = int(match.group("month"))
    if not 1 <= month <= 12:
        raise ValueError(f"invalid instrument month: {instrument_id}")
    strike_text = match.group("strike")
    return Instrument(
        instrument_id=instrument_id,
        product=match.group("product"),
        year=int(match.group("year")),
        month=month,
        cp=match.group("cp"),
        strike=float(strike_text) if strike_text is not None else None,
    )


def net_positions(portfolio: dict[str, Any]) -> dict[str, float]:
    quantities: dict[str, Decimal] = defaultdict(Decimal)
    for row in portfolio["positions"]:
        quantities[row["instrument_id"]] += _decimal(row["qty"])
    return {instrument_id: float(qty) for instrument_id, qty in quantities.items() if qty != 0}


def product_of(instrument_id: str) -> str:
    return _parse_instrument(instrument_id).product


def is_option(instrument_id: str) -> bool:
    return _parse_instrument(instrument_id).is_option


def _effective_psr(inst: Instrument, forward: float, product: dict[str, Any], house: dict[str, Any],
                   valuation_date: date) -> float:
    delivery_days = (date(inst.year, inst.month, 1) - valuation_date).days
    if delivery_days <= int(house["delivery_scale_days"]):
        scale = 1.0
    else:
        scale = max(math.sqrt(delivery_days / 365.0), float(house["delivery_scale_floor"]))
    return float(product["price_scan_range"]) * scale


def _shocked_forward(forward: float, price_multiplier: float, effective_psr: float, mode: str) -> float:
    if mode == "linear":
        shocked = forward + price_multiplier * effective_psr
    elif mode == "log":
        shocked = forward * math.exp(price_multiplier * effective_psr / forward) if forward > 0 else 1e-8
    else:
        raise ValueError(f"invalid shock_mode: {mode}")
    return max(shocked, 1e-8)


def _calculate_position(inst: Instrument, qty: float, product: dict[str, Any], market: dict[str, Any],
                        house: dict[str, Any], valuation_date: date) -> PositionCalc:
    forward = float(market["futures_price"][inst.future_id])
    multiplier = float(product["multiplier"])
    effective_psr = _effective_psr(inst, forward, product, house, valuation_date)
    scenario_pl: list[Decimal] = []
    scenario_deltas: list[float] = []

    if inst.is_option:
        vol = float(market["atm_vol"][inst.instrument_id])
        expiry = date.fromisoformat(market["option_expiry"][inst.instrument_id])
        t = year_fraction(valuation_date, expiry)
        assert inst.strike is not None and inst.cp is not None
        is_call = inst.cp == "C"
        base_value = black_price(forward, inst.strike, vol, t, is_call)
        atm_delta = black_delta(forward, inst.strike, vol, t, is_call)
    else:
        vol = 0.0
        t = 0.0
        is_call = False
        base_value = 0.0
        atm_delta = 1.0

    for index, price_multiplier in enumerate(PRICE_MULT):
        shocked_forward = _shocked_forward(
            forward, price_multiplier, effective_psr, str(product["shock_mode"])
        )
        weight = PL_WEIGHT[index]
        if inst.is_option:
            fraction = (float(product["vol_scan_fraction"]) if VOL_DIRECTION[index] > 0
                        else -float(product["vsf_down"]))
            shocked_vol = max(vol * (1.0 + fraction), 1e-6)
            shocked_value = black_price(shocked_forward, inst.strike, shocked_vol, t, is_call)  # type: ignore[arg-type]
            raw_pl = qty * (shocked_value - base_value) * multiplier * weight
            scenario_deltas.append(
                black_delta(shocked_forward, inst.strike, shocked_vol, t, is_call)  # type: ignore[arg-type]
            )
        else:
            raw_pl = qty * (shocked_forward - forward) * multiplier * weight
            scenario_deltas.append(1.0)
        scenario_pl.append(scenario_money(raw_pl))

    return PositionCalc(inst, qty, product, scenario_pl, scenario_deltas, atm_delta, base_value)


def _month_date(bucket: str) -> date:
    year, month = (int(part) for part in bucket.split("-"))
    return date(year, month, 1)


def _months_apart(left: str, right: str) -> int:
    ly, lm = (int(part) for part in left.split("-"))
    ry, rm = (int(part) for part in right.split("-"))
    return (ry * 12 + rm) - (ly * 12 + lm)


def _intra_and_strip(bucket_delta: dict[str, float], product: dict[str, Any]) -> tuple[Decimal, Decimal, float]:
    remaining = dict(bucket_delta)
    charge = 0.0
    tiers = product["intra_tiers"]

    while True:
        nonzero = [(bucket, value) for bucket, value in remaining.items() if value != 0.0]
        if not nonzero:
            break
        bucket_a, delta_a = min(nonzero, key=lambda item: (-abs(item[1]), item[0]))
        opposites = [(bucket, value) for bucket, value in nonzero if value * delta_a < 0.0]
        if not opposites:
            break
        date_a = _month_date(bucket_a)
        bucket_b, delta_b = min(
            opposites,
            key=lambda item: (abs((_month_date(item[0]) - date_a).days), -abs(item[1]), item[0]),
        )
        matched = min(abs(delta_a), abs(delta_b))
        distance = abs((_month_date(bucket_b) - date_a).days)
        if distance <= 32:
            rate = float(tiers["adjacent"])
        elif distance <= 125:
            rate = float(tiers["mid"])
        else:
            rate = float(tiers["back"])
        charge += matched * rate * math.sqrt(distance / 365.0)

        if abs(delta_a) <= abs(delta_b):
            remaining[bucket_a] = 0.0
        else:
            remaining[bucket_a] = math.copysign(abs(delta_a) - matched, delta_a)
        if abs(delta_b) <= abs(delta_a):
            remaining[bucket_b] = 0.0
        else:
            remaining[bucket_b] = math.copysign(abs(delta_b) - matched, delta_b)

    strip = 0.0
    strip_rate = float(product["strip_rate"])
    active = sorted(bucket for bucket, value in remaining.items() if value != 0.0)
    if strip_rate != 0.0 and active:
        run: list[str] = [active[0]]
        runs: list[list[str]] = []
        for bucket in active[1:]:
            if _months_apart(run[-1], bucket) == 1:
                run.append(bucket)
            else:
                runs.append(run)
                run = [bucket]
        runs.append(run)
        for run in runs:
            if len(run) >= 3:
                strip += (len(run) - 2) * strip_rate * min(abs(remaining[bucket]) for bucket in run)

    outright = math.fsum(remaining.values())
    return rounded_formula(charge), rounded_formula(strip), outright


def _cc_config(products: dict[str, Any], positions: list[PositionCalc]) -> dict[str, Any]:
    """Select the CC-level terms, rejecting an undefined mixed setup."""

    configs = {position.instrument.product: position.product_config for position in positions}
    first_name = min(configs)
    first = configs[first_name]
    cc_fields = (
        "cc_id", "ics_group", "currency", "strip_rate", "concentration_threshold",
        "concentration_rate", "intra_tiers",
    )
    for name, candidate in configs.items():
        if any(candidate[field] != first[field] for field in cc_fields):
            raise ValueError(f"products {first_name} and {name} have incompatible CC-level settings")
    return first


def _credit_cents(row: dict[str, Any], units: int) -> int:
    amount = Decimal(units) * _decimal(row["credit_per_unit"]) * (Decimal(1) - _decimal(row["rho"]))
    return int(q2(amount) / CENT)


def _simplex_max(constraints: list[list[int]], bounds: list[int], objective: list[int]) -> tuple[Fraction, list[Fraction]]:
    """Solve a feasible packing LP exactly with a rational primal simplex."""

    variable_count = len(objective)
    row_count = len(constraints)
    width = variable_count + row_count + 1
    tableau: list[list[Fraction]] = []
    basis: list[int] = []
    for row_index, (coefficients, bound) in enumerate(zip(constraints, bounds)):
        row = [Fraction(value) for value in coefficients]
        row.extend(Fraction(int(index == row_index)) for index in range(row_count))
        row.append(Fraction(bound))
        tableau.append(row)
        basis.append(variable_count + row_index)
    objective_row = [Fraction(-value) for value in objective]
    objective_row.extend(Fraction(0) for _ in range(row_count + 1))
    tableau.append(objective_row)

    while True:
        entering = next((column for column in range(width - 1) if tableau[-1][column] < 0), None)
        if entering is None:
            break
        candidates = [
            (tableau[row][-1] / tableau[row][entering], basis[row], row)
            for row in range(row_count)
            if tableau[row][entering] > 0
        ]
        if not candidates:
            raise ValueError("unbounded inter-spread optimization")
        _, _, leaving = min(candidates)
        pivot = tableau[leaving][entering]
        tableau[leaving] = [value / pivot for value in tableau[leaving]]
        for row in range(row_count + 1):
            if row == leaving or tableau[row][entering] == 0:
                continue
            factor = tableau[row][entering]
            tableau[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(tableau[row], tableau[leaving])
            ]
        basis[leaving] = entering

    solution = [Fraction(0) for _ in range(variable_count)]
    for row, basic_variable in enumerate(basis):
        if basic_variable < variable_count:
            solution[basic_variable] = tableau[row][-1]
    return tableau[-1][-1], solution


def _linear_integer_allocation(vectors: list[tuple[int, ...]], capacities: tuple[int, ...],
                               credit_per_unit: list[int]) -> tuple[int, ...]:
    """Solve the common whole-cent-credit ILP exactly and lexicographically."""

    row_count = len(vectors)
    maximums = [
        min(capacities[index] // ratio for index, ratio in enumerate(vector) if ratio)
        for vector in vectors
    ]

    # Encode the primary credit and the complete config-order unit tie-break
    # into one exact integer linear objective.
    radix = 1
    lex_weights = [0] * row_count
    for index in range(row_count - 1, -1, -1):
        lex_weights[index] = radix
        radix *= maximums[index] + 1
    objective = [credit_per_unit[index] * radix + lex_weights[index] for index in range(row_count)]

    resource_constraints = [
        [vectors[row][resource] for row in range(row_count)]
        for resource in range(len(capacities))
    ]
    best_value = -1
    best_solution = tuple(0 for _ in range(row_count))

    def search(lower: tuple[int, ...], upper: tuple[int, ...]) -> None:
        nonlocal best_value, best_solution
        shifted_bounds = [
            capacities[resource]
            - sum(resource_constraints[resource][row] * lower[row] for row in range(row_count))
            for resource in range(len(capacities))
        ]
        if any(value < 0 for value in shifted_bounds):
            return
        constraints = [row[:] for row in resource_constraints]
        bounds = shifted_bounds[:]
        for row in range(row_count):
            coefficients = [0] * row_count
            coefficients[row] = 1
            constraints.append(coefficients)
            bounds.append(upper[row] - lower[row])
        lp_shifted, shifted_solution = _simplex_max(constraints, bounds, objective)
        lower_value = sum(objective[row] * lower[row] for row in range(row_count))
        lp_value = lp_shifted + lower_value
        if lp_value.numerator // lp_value.denominator <= best_value:
            return
        solution = [shifted_solution[row] + lower[row] for row in range(row_count)]
        fractional = next((row for row, value in enumerate(solution) if value.denominator != 1), None)
        if fractional is None:
            integer_solution = tuple(int(value) for value in solution)
            value = sum(objective[row] * integer_solution[row] for row in range(row_count))
            if value > best_value:
                best_value, best_solution = value, integer_solution
            return

        value = solution[fractional]
        floor_value = value.numerator // value.denominator
        ceil_value = floor_value + 1
        # Explore the high branch first to find config-lexicographically large
        # incumbents early; the exact LP bound still determines correctness.
        if ceil_value <= upper[fractional]:
            high_lower = list(lower)
            high_lower[fractional] = ceil_value
            search(tuple(high_lower), upper)
        if floor_value >= lower[fractional]:
            low_upper = list(upper)
            low_upper[fractional] = floor_value
            search(lower, tuple(low_upper))

    search(tuple(0 for _ in range(row_count)), tuple(maximums))
    return best_solution


def _optimize_inter_spreads(rows: list[dict[str, Any]], commodities: dict[str, CommodityCalc]) -> list[int]:
    """Return the exact credit-maximizing integer allocation."""

    admissible: list[tuple[int, dict[str, Any], dict[str, int]]] = []
    for config_index, row in enumerate(rows):
        legs = row["legs"]
        base_legs = [leg for leg in legs if leg["role"] == "base"]
        opp_legs = [leg for leg in legs if leg["role"] == "opp"]
        if len(base_legs) != 1 or not opp_legs:
            continue
        cc_ids = [leg["cc"] for leg in legs]
        if len(set(cc_ids)) != len(cc_ids) or any(cc not in commodities for cc in cc_ids):
            continue
        involved = [commodities[cc] for cc in cc_ids]
        if any(cc.outright_delta == 0.0 for cc in involved):
            continue
        if any(cc.ics_group != row["ics_group"] or cc.currency != involved[0].currency for cc in involved):
            continue
        base_delta = commodities[base_legs[0]["cc"]].outright_delta
        if any(commodities[leg["cc"]].outright_delta * base_delta >= 0.0 for leg in opp_legs):
            continue
        ratios: dict[str, int] = {}
        valid = True
        for leg in legs:
            ratio = int(leg["ratio"])
            if ratio <= 0:
                valid = False
                break
            ratios[leg["cc"]] = ratio
        if valid:
            admissible.append((config_index, row, ratios))

    allocations = [0] * len(rows)
    if not admissible:
        return allocations

    resource_ids = sorted({cc for _, _, ratios in admissible for cc in ratios})
    resource_index = {cc: index for index, cc in enumerate(resource_ids)}
    capacities = tuple(math.floor(abs(commodities[cc].outright_delta)) for cc in resource_ids)
    vectors: list[tuple[int, ...]] = []
    for _, _, ratios in admissible:
        vector = [0] * len(resource_ids)
        for cc, ratio in ratios.items():
            vector[resource_index[cc]] = ratio
        vectors.append(tuple(vector))

    per_unit_cents: list[int] = []
    credits_are_linear = True
    for _, row, _ in admissible:
        exact_cents = (
            _decimal(row["credit_per_unit"])
            * (Decimal(1) - _decimal(row["rho"]))
            / CENT
        )
        if exact_cents != exact_cents.to_integral_value():
            credits_are_linear = False
            break
        per_unit_cents.append(int(exact_cents))
    if credits_are_linear:
        selected = _linear_integer_allocation(vectors, capacities, per_unit_cents)
        for item, units in zip(admissible, selected):
            allocations[item[0]] = units
        return allocations

    @lru_cache(maxsize=None)
    def solve(index: int, remaining: tuple[int, ...]) -> tuple[int, tuple[int, ...]]:
        if index == len(admissible):
            return 0, ()
        vector = vectors[index]
        maximum = min(remaining[i] // ratio for i, ratio in enumerate(vector) if ratio)
        if index == len(admissible) - 1:
            row = admissible[index][1]
            # Credits are non-negative by definition. The largest feasible
            # unit count therefore also wins the config-order tie if several
            # rounded totals coincide.
            return _credit_cents(row, maximum), (maximum,)
        best_score: int | None = None
        best_units: tuple[int, ...] = ()
        row = admissible[index][1]
        # Descending iteration establishes the config-order unit tie-break.
        for units in range(maximum, -1, -1):
            next_remaining = tuple(value - units * vector[i] for i, value in enumerate(remaining))
            tail_score, tail_units = solve(index + 1, next_remaining)
            score = _credit_cents(row, units) + tail_score
            candidate = (units,) + tail_units
            if best_score is None or score > best_score or (score == best_score and candidate > best_units):
                best_score, best_units = score, candidate
        assert best_score is not None
        return best_score, best_units

    _, selected = solve(0, capacities)
    for item, units in zip(admissible, selected):
        allocations[item[0]] = units
    return allocations


def _apply_inter_spreads(rows: list[dict[str, Any]], allocations: list[int],
                         commodities: dict[str, CommodityCalc]) -> None:
    consumed: dict[str, int] = defaultdict(int)
    for row, units in zip(rows, allocations):
        if units == 0:
            continue
        credit = Decimal(_credit_cents(row, units)) * CENT
        legs = row["legs"]
        share = q2(credit / len(legs))
        for index, leg in enumerate(legs):
            leg_share = share if index < len(legs) - 1 else credit - share * (len(legs) - 1)
            commodities[leg["cc"]].inter_credit += leg_share
            consumed[leg["cc"]] += units * int(leg["ratio"])

    for cc_id, commodity in commodities.items():
        delta = commodity.outright_delta
        used = consumed[cc_id]
        commodity.residual_delta = math.copysign(max(0.0, abs(delta) - used), delta) if delta else 0.0
        commodity.inter_credit = q2(commodity.inter_credit)


def compute_report(portfolio: dict[str, Any], market: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    valuation_date = date.fromisoformat(market["valuation_date"])
    products = config["products"]
    net = net_positions(portfolio)

    position_groups: dict[str, list[PositionCalc]] = defaultdict(list)
    for instrument_id in sorted(net):
        inst = _parse_instrument(instrument_id)
        product = products[inst.product]
        calculated = _calculate_position(
            inst, net[instrument_id], product, market, config["house"], valuation_date
        )
        position_groups[product["cc_id"]].append(calculated)

    commodities: dict[str, CommodityCalc] = {}
    for cc_id, positions in position_groups.items():
        product = _cc_config(products, positions)
        scenario_pl = [Decimal("0.00") for _ in range(16)]
        for position in positions:
            for index, value in enumerate(position.scenario_pl):
                scenario_pl[index] += value
        worst_index = min(range(16), key=lambda index: (scenario_pl[index], index + 1))
        scan = q2(max(Decimal(0), -scenario_pl[worst_index]))
        commodity = CommodityCalc(
            cc_id=cc_id,
            config=product,
            currency=product["currency"],
            ics_group=product["ics_group"],
            positions=positions,
            scenario_pl=scenario_pl,
            worst_scenario_id=worst_index + 1,
            scanning_risk=scan,
        )

        if commodity.worst_scenario_id <= 14:
            candidates = [index for index in range(14) if index != worst_index]
            next_index = min(candidates, key=lambda index: (scenario_pl[index], index + 1))
            delta_indices = (worst_index, next_index)
        else:
            delta_indices = (worst_index,)

        bucket_parts: dict[str, list[float]] = defaultdict(list)
        for position in positions:
            composite = math.fsum(position.scenario_delta[index] for index in delta_indices) / len(delta_indices)
            bucket_parts[position.instrument.bucket].append(composite * position.qty)
        bucket_delta = {bucket: math.fsum(values) for bucket, values in bucket_parts.items()}
        commodity.intra_charge, commodity.strip_credit, commodity.outright_delta = _intra_and_strip(
            bucket_delta, product
        )

        som_value = 0.0
        nov_value = 0.0
        liquidity_value = 0.0
        for position in positions:
            if not position.instrument.is_option:
                continue
            abs_delta = abs(position.atm_delta)
            if position.qty < 0:
                som_value += (float(position.product_config["som_rate"]) * abs(position.qty)
                              * (1.0 + max(0.0, 0.25 - abs_delta)))
                liquidity_value += (float(position.product_config["lao_rate"]) * abs(position.qty)
                                    * max(0.0, float(position.product_config["lao_otm"]) - abs_delta))
            elif abs_delta < 0.35:
                nov_value += max(
                    0.0,
                    position.qty * position.option_value * float(position.product_config["multiplier"]),
                )
        commodity.som = rounded_formula(som_value)
        methodology_nov = rounded_formula(nov_value)
        commodity.nov_credit = q2(min(methodology_nov, commodity.scanning_risk))
        commodity.liquidity_addon = rounded_formula(liquidity_value)
        commodities[cc_id] = commodity

    allocations = _optimize_inter_spreads(config["inter_spreads"], commodities)
    _apply_inter_spreads(config["inter_spreads"], allocations, commodities)

    fx = {currency: _decimal(rate) for currency, rate in market["fx_to_usd"].items()}
    rows: list[dict[str, Any]] = []
    total = Decimal("0.00")
    for cc_id in sorted(commodities):
        commodity = commodities[cc_id]
        threshold = float(commodity.config["concentration_threshold"])
        rate = float(commodity.config["concentration_rate"])
        concentration = max(0.0, abs(commodity.residual_delta) - threshold) * rate
        commodity.concentration_charge = rounded_formula(concentration)
        raw = q2(
            commodity.scanning_risk
            + commodity.intra_charge
            + commodity.concentration_charge
            - commodity.inter_credit
            - commodity.nov_credit
            - commodity.strip_credit
        )
        native = q2(max(raw, commodity.som) + commodity.liquidity_addon)
        usd = q2(native * fx[commodity.currency])
        total += usd
        rows.append(
            {
                "cc_id": cc_id,
                "currency": commodity.currency,
                "scanning_risk": float(commodity.scanning_risk),
                "intra_charge": float(commodity.intra_charge),
                "inter_credit": float(commodity.inter_credit),
                "nov_credit": float(commodity.nov_credit),
                "som": float(commodity.som),
                "strip_credit": float(commodity.strip_credit),
                "concentration_charge": float(commodity.concentration_charge),
                "liquidity_addon": float(commodity.liquidity_addon),
                "raw_margin": float(raw),
                "cc_margin_native": float(native),
                "cc_margin_usd": float(usd),
                "worst_scenario_id": commodity.worst_scenario_id,
            }
        )

    return {
        "valuation_date": market["valuation_date"],
        "currency": "USD",
        "total_margin_usd": float(q2(total)),
        "combined_commodities": rows,
    }


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def _render_json(value: Any, level: int = 0) -> str:
    indent = "  " * level
    child_indent = "  " * (level + 1)
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = [f"{child_indent}{json.dumps(str(key))}: {_render_json(item, level + 1)}"
                 for key, item in value.items()]
        return "{\n" + ",\n".join(items) + f"\n{indent}}}"
    if isinstance(value, list):
        if not value:
            return "[]"
        items = [f"{child_indent}{_render_json(item, level + 1)}" for item in value]
        return "[\n" + ",\n".join(items) + f"\n{indent}]"
    if isinstance(value, bool) or value is None:
        return json.dumps(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (float, Decimal)):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("margin report contains a non-finite number")
        return format(number, ".2f")
    return json.dumps(value)


def write_report(report: dict[str, Any], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_render_json(report) + "\n")
