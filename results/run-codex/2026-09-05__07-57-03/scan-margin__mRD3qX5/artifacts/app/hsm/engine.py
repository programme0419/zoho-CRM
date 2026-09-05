"""House Scan Margin calculation engine."""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal, getcontext
from pathlib import Path
from typing import Any

try:  # Supports both ``python hsm/run_margin.py`` and package-style imports.
    from .lib.black76 import delta as black_delta
    from .lib.black76 import price as black_price
    from .lib.black76 import year_fraction
except ImportError:  # pragma: no cover - this is the CLI import path
    from lib.black76 import delta as black_delta
    from lib.black76 import price as black_price
    from lib.black76 import year_fraction


getcontext().prec = 60
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
VOL_UP = (True, False) * 8
PL_WEIGHT = (1.0,) * 14 + (0.28, 0.28)

_INSTRUMENT_RE = re.compile(
    r"^(?P<product>[^-]+)-(?P<year>\d{4})-(?P<month>\d{2})"
    r"(?:-(?P<cp>[CP])-(?P<strike>\d+\.\d{2}))?$"
)
_MONEY_FIELDS = {
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
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def q2(value: Any) -> Decimal:
    result = _decimal(value).quantize(CENT, rounding=ROUND_HALF_EVEN)
    return ZERO if result == 0 else result


def money(value: float) -> Decimal:
    """The special per-position/scenario conversion required by section 3."""

    return q2(Decimal(format(float(value), ".10f")))


def net_positions(portfolio: dict) -> dict[str, Decimal]:
    quantities: dict[str, Decimal] = defaultdict(Decimal)
    for row in portfolio["positions"]:
        quantities[row["instrument_id"]] += _decimal(row["qty"])
    return {
        instrument_id: qty
        for instrument_id, qty in quantities.items()
        if qty != 0
    }


@dataclass
class Position:
    instrument_id: str
    qty_decimal: Decimal
    product_name: str
    product: dict
    month_key: str
    forward: float
    price_shocks: tuple[float, ...]
    is_option: bool
    cp: str | None = None
    strike: float = 0.0
    vol: float = 0.0
    t: float = 0.0
    base_value: float = 0.0
    atm_delta: float = 1.0
    scenario_values: tuple[float, ...] = ()
    scenario_deltas: tuple[float, ...] = ()

    @property
    def qty(self) -> float:
        return float(self.qty_decimal)


@dataclass
class Commodity:
    cc_id: str
    product_names: list[str]
    positions: list[Position]
    product: dict
    currency: str
    ics_group: str
    scenario_pl: list[Decimal] = field(default_factory=list)
    scanning_risk: Decimal = ZERO
    worst_scenario_id: int = 1
    bucket_deltas: dict[str, float] = field(default_factory=dict)
    remaining_buckets: dict[str, float] = field(default_factory=dict)
    intra_charge: Decimal = ZERO
    strip_credit: Decimal = ZERO
    outright_delta: float = 0.0
    residual_delta: float = 0.0
    inter_credit: Decimal = ZERO
    nov_credit: Decimal = ZERO
    som: Decimal = ZERO
    concentration_charge: Decimal = ZERO
    liquidity_addon: Decimal = ZERO


def _parse_instrument(instrument_id: str) -> tuple[str, int, int, str | None, float]:
    match = _INSTRUMENT_RE.fullmatch(instrument_id)
    if match is None:
        raise ValueError(f"invalid instrument_id: {instrument_id}")
    year = int(match.group("year"))
    month = int(match.group("month"))
    if not 1 <= month <= 12:
        raise ValueError(f"invalid instrument month: {instrument_id}")
    cp = match.group("cp")
    strike = float(match.group("strike")) if cp is not None else 0.0
    return match.group("product"), year, month, cp, strike


def _effective_psr(
    product: dict, house: dict, valuation_date: date, year: int, month: int
) -> float:
    days_to_delivery = (date(year, month, 1) - valuation_date).days
    if days_to_delivery <= int(house["delivery_scale_days"]):
        scale = 1.0
    else:
        scale = max(
            math.sqrt(days_to_delivery / 365.0),
            float(house["delivery_scale_floor"]),
        )
    return float(product["price_scan_range"]) * scale


def _price_shocks(forward: float, psr: float, mode: str) -> tuple[float, ...]:
    shocks: list[float] = []
    for multiplier in PRICE_MULT:
        if mode == "linear":
            shocked = forward + multiplier * psr
        elif mode == "log":
            shocked = (
                forward * math.exp(multiplier * psr / forward)
                if forward > 0.0
                else 1e-8
            )
        else:
            raise ValueError(f"invalid shock_mode: {mode}")
        shocks.append(max(shocked, 1e-8))
    return tuple(shocks)


def _make_position(
    instrument_id: str,
    qty: Decimal,
    products: dict,
    market: dict,
    house: dict,
    valuation_date: date,
) -> Position:
    product_name, year, month, cp, strike = _parse_instrument(instrument_id)
    product = products[product_name]
    month_key = f"{year:04d}-{month:02d}"
    future_id = f"{product_name}-{month_key}"
    forward = float(market["futures_price"][future_id])
    psr = _effective_psr(product, house, valuation_date, year, month)
    shocks = _price_shocks(forward, psr, product["shock_mode"])

    if cp is None:
        return Position(
            instrument_id=instrument_id,
            qty_decimal=qty,
            product_name=product_name,
            product=product,
            month_key=month_key,
            forward=forward,
            price_shocks=shocks,
            is_option=False,
            scenario_deltas=(1.0,) * 16,
        )

    vol = float(market["atm_vol"][instrument_id])
    expiry = date.fromisoformat(market["option_expiry"][instrument_id])
    t = year_fraction(valuation_date, expiry)
    is_call = cp == "C"
    base_value = black_price(forward, strike, vol, t, is_call)
    atm_delta = black_delta(forward, strike, vol, t, is_call)
    values: list[float] = []
    deltas: list[float] = []
    up_fraction = float(product["vol_scan_fraction"])
    down_fraction = float(product["vsf_down"])
    for scenario_index, shocked_forward in enumerate(shocks):
        signed_fraction = up_fraction if VOL_UP[scenario_index] else -down_fraction
        shocked_vol = max(vol * (1.0 + signed_fraction), 1e-6)
        values.append(black_price(shocked_forward, strike, shocked_vol, t, is_call))
        deltas.append(black_delta(shocked_forward, strike, shocked_vol, t, is_call))
    return Position(
        instrument_id=instrument_id,
        qty_decimal=qty,
        product_name=product_name,
        product=product,
        month_key=month_key,
        forward=forward,
        price_shocks=shocks,
        is_option=True,
        cp=cp,
        strike=strike,
        vol=vol,
        t=t,
        base_value=base_value,
        atm_delta=atm_delta,
        scenario_values=tuple(values),
        scenario_deltas=tuple(deltas),
    )


def _position_scenario_pl(position: Position, scenario_index: int) -> Decimal:
    multiplier = float(position.product["multiplier"])
    if position.is_option:
        change = position.scenario_values[scenario_index] - position.base_value
    else:
        change = position.price_shocks[scenario_index] - position.forward
    raw = position.qty * change * multiplier * PL_WEIGHT[scenario_index]
    return money(raw)


def _scan_and_deltas(commodity: Commodity) -> None:
    commodity.scenario_pl = []
    for scenario_index in range(16):
        scenario_total = ZERO
        for position in commodity.positions:
            scenario_total += _position_scenario_pl(position, scenario_index)
        commodity.scenario_pl.append(scenario_total)

    worst_index = min(range(16), key=lambda index: (commodity.scenario_pl[index], index))
    commodity.worst_scenario_id = worst_index + 1
    commodity.scanning_risk = q2(max(Decimal(0), -commodity.scenario_pl[worst_index]))

    if worst_index < 14:
        second_index = min(
            (index for index in range(14) if index != worst_index),
            key=lambda index: (commodity.scenario_pl[index], index),
        )
        delta_indices = (worst_index, second_index)
    else:
        delta_indices = (worst_index,)

    bucket_deltas: dict[str, float] = defaultdict(float)
    for position in commodity.positions:
        per_contract = sum(position.scenario_deltas[i] for i in delta_indices) / len(
            delta_indices
        )
        bucket_deltas[position.month_key] += per_contract * position.qty
    commodity.bucket_deltas = dict(bucket_deltas)


def _month_date(month_key: str) -> date:
    return date(int(month_key[0:4]), int(month_key[5:7]), 1)


def _intra_spread(commodity: Commodity) -> None:
    remaining = dict(commodity.bucket_deltas)
    total_charge = 0.0
    tiers = commodity.product["intra_tiers"]

    while True:
        nonzero = [key for key, value in remaining.items() if value != 0.0]
        opposite_exists = any(
            remaining[left] * remaining[right] < 0.0
            for position, left in enumerate(nonzero)
            for right in nonzero[position + 1 :]
        )
        if not opposite_exists:
            break

        bucket_a = min(nonzero, key=lambda key: (-abs(remaining[key]), key))
        date_a = _month_date(bucket_a)
        candidates = [
            key for key in nonzero if remaining[key] * remaining[bucket_a] < 0.0
        ]
        bucket_b = min(
            candidates,
            key=lambda key: (
                abs((_month_date(key) - date_a).days),
                -abs(remaining[key]),
                key,
            ),
        )
        matched = min(abs(remaining[bucket_a]), abs(remaining[bucket_b]))
        days = abs((_month_date(bucket_b) - date_a).days)
        if days <= 32:
            rate = float(tiers["adjacent"])
        elif days <= 125:
            rate = float(tiers["mid"])
        else:
            rate = float(tiers["back"])
        total_charge += matched * rate * math.sqrt(days / 365.0)

        sign_a = 1.0 if remaining[bucket_a] > 0.0 else -1.0
        sign_b = 1.0 if remaining[bucket_b] > 0.0 else -1.0
        remaining[bucket_a] -= sign_a * matched
        remaining[bucket_b] -= sign_b * matched
        if remaining[bucket_a] == -0.0:
            remaining[bucket_a] = 0.0
        if remaining[bucket_b] == -0.0:
            remaining[bucket_b] = 0.0

    commodity.intra_charge = q2(total_charge)
    commodity.remaining_buckets = remaining
    commodity.outright_delta = sum(remaining.values())
    commodity.residual_delta = commodity.outright_delta


def _month_ordinal(month_key: str) -> int:
    return int(month_key[0:4]) * 12 + int(month_key[5:7]) - 1


def _strip_credit(commodity: Commodity) -> None:
    rate = float(commodity.product["strip_rate"])
    months = sorted(
        key for key, delta in commodity.remaining_buckets.items() if delta != 0.0
    )
    if rate == 0.0 or len(months) < 3:
        commodity.strip_credit = ZERO
        return

    runs: list[list[str]] = []
    run: list[str] = []
    for month in months:
        if run and _month_ordinal(month) != _month_ordinal(run[-1]) + 1:
            runs.append(run)
            run = []
        run.append(month)
    if run:
        runs.append(run)

    credit = 0.0
    for current in runs:
        if len(current) >= 3:
            minimum_delta = min(abs(commodity.remaining_buckets[key]) for key in current)
            credit += (len(current) - 2) * rate * minimum_delta
    commodity.strip_credit = q2(credit)


@dataclass(frozen=True)
class SpreadCandidate:
    config_index: int
    row: dict
    consumption: tuple[tuple[str, int], ...]
    credit_factor: Decimal

    def credit(self, units: int) -> Decimal:
        return q2(Decimal(units) * self.credit_factor)


def _spread_candidate(
    config_index: int, row: dict, commodities: dict[str, Commodity]
) -> SpreadCandidate | None:
    legs = row["legs"]
    base_legs = [leg for leg in legs if leg["role"] == "base"]
    opp_legs = [leg for leg in legs if leg["role"] == "opp"]
    if len(base_legs) != 1 or not opp_legs:
        return None
    if any(leg["cc"] not in commodities or int(leg["ratio"]) <= 0 for leg in legs):
        return None

    leg_commodities = [commodities[leg["cc"]] for leg in legs]
    if any(cc.outright_delta == 0.0 for cc in leg_commodities):
        return None
    currencies = {cc.currency for cc in leg_commodities}
    groups = {cc.ics_group for cc in leg_commodities}
    if len(currencies) != 1 or groups != {row["ics_group"]}:
        return None

    base_delta = commodities[base_legs[0]["cc"]].outright_delta
    if any(base_delta * commodities[leg["cc"]].outright_delta >= 0.0 for leg in opp_legs):
        return None

    by_cc: dict[str, int] = defaultdict(int)
    for leg in legs:
        by_cc[leg["cc"]] += int(leg["ratio"])
    factor = _decimal(row["credit_per_unit"]) * (Decimal(1) - _decimal(row["rho"]))
    return SpreadCandidate(config_index, row, tuple(by_cc.items()), factor)


def _candidate_components(candidates: list[SpreadCandidate]) -> list[list[int]]:
    """Partition rows that cannot compete for the same CC capacity."""

    cc_to_rows: dict[str, list[int]] = defaultdict(list)
    for row_index, candidate in enumerate(candidates):
        for cc_id, _ratio in candidate.consumption:
            cc_to_rows[cc_id].append(row_index)

    unseen = set(range(len(candidates)))
    components: list[list[int]] = []
    while unseen:
        seed = min(unseen)
        stack = [seed]
        unseen.remove(seed)
        component: list[int] = []
        while stack:
            row_index = stack.pop()
            component.append(row_index)
            for cc_id, _ratio in candidates[row_index].consumption:
                for neighbor in cc_to_rows[cc_id]:
                    if neighbor in unseen:
                        unseen.remove(neighbor)
                        stack.append(neighbor)
        components.append(sorted(component))
    return components


def _solve_component(
    component: list[SpreadCandidate], capacities: dict[str, int]
) -> tuple[int, ...]:
    resources = sorted(
        {cc_id for candidate in component for cc_id, _ in candidate.consumption}
    )
    resource_index = {cc_id: index for index, cc_id in enumerate(resources)}
    initial = tuple(capacities[cc_id] for cc_id in resources)
    consumption = [
        tuple((resource_index[cc_id], ratio) for cc_id, ratio in candidate.consumption)
        for candidate in component
    ]

    # The common two-commodity case has just one row. Avoid a capacity-sized
    # dynamic program for large institutional books. A non-negative credit is
    # monotone in units, and config-order tie-breaking also prefers the maximum.
    if len(component) == 1 and component[0].credit_factor >= 0:
        maximum = min(initial[index] // ratio for index, ratio in consumption[0])
        return (maximum,)

    # Search high-value rows first to get a strong incumbent, but compare final
    # allocations in original config order. The independent-row bound is an
    # admissible upper bound because it ignores competition for capacities.
    def search_score(row_index: int) -> tuple[float, int]:
        normalized_use = sum(
            ratio / max(1, initial[resource])
            for resource, ratio in consumption[row_index]
        )
        factor = max(0.0, float(component[row_index].credit_factor))
        return (-(factor / normalized_use if normalized_use else factor), row_index)

    search_order = sorted(range(len(component)), key=search_score)
    credit_cache: dict[tuple[int, int], Decimal] = {}

    def row_credit(row_index: int, units: int) -> Decimal:
        key = (row_index, units)
        if key not in credit_cache:
            credit_cache[key] = component[row_index].credit(units)
        return credit_cache[key]

    def maximum_units(row_index: int, remaining: tuple[int, ...]) -> int:
        return min(
            remaining[resource] // ratio
            for resource, ratio in consumption[row_index]
        )

    best_credit: Decimal | None = None
    best_allocation: tuple[int, ...] | None = None
    current_allocation = [0] * len(component)
    best_seen: dict[tuple[int, tuple[int, ...]], Decimal] = {}

    def visit(depth: int, remaining: tuple[int, ...], accrued: Decimal) -> None:
        nonlocal best_credit, best_allocation
        state = (depth, remaining)
        previous = best_seen.get(state)
        if previous is not None and accrued < previous:
            return
        if previous is None or accrued > previous:
            best_seen[state] = accrued

        if depth == len(search_order):
            allocation = tuple(current_allocation)
            if (
                best_credit is None
                or accrued > best_credit
                or (accrued == best_credit and allocation > best_allocation)
            ):
                best_credit = accrued
                best_allocation = allocation
            return

        upper = accrued
        optimistic_allocation = list(current_allocation)
        for later_depth in range(depth, len(search_order)):
            row_index = search_order[later_depth]
            maximum = maximum_units(row_index, remaining)
            optimistic_allocation[row_index] = maximum
            if component[row_index].credit_factor >= 0:
                upper += row_credit(row_index, maximum)
        if best_credit is not None:
            if upper < best_credit:
                return
            if (
                upper == best_credit
                and best_allocation is not None
                and tuple(optimistic_allocation) <= best_allocation
            ):
                return

        row_index = search_order[depth]
        maximum = maximum_units(row_index, remaining)
        unit_range = (
            range(maximum, -1, -1)
            if component[row_index].credit_factor >= 0
            else range(0, maximum + 1)
        )
        for units in unit_range:
            next_remaining = list(remaining)
            for resource, ratio in consumption[row_index]:
                next_remaining[resource] -= units * ratio
            current_allocation[row_index] = units
            visit(
                depth + 1,
                tuple(next_remaining),
                accrued + row_credit(row_index, units),
            )
        current_allocation[row_index] = 0

    visit(0, initial, ZERO)
    assert best_allocation is not None
    return best_allocation


def _inter_spreads(commodities: dict[str, Commodity], rows: list[dict]) -> None:
    candidates = [
        candidate
        for index, row in enumerate(rows)
        if (candidate := _spread_candidate(index, row, commodities)) is not None
    ]
    if not candidates:
        return

    capacities = {
        cc_id: math.floor(abs(commodity.outright_delta))
        for cc_id, commodity in commodities.items()
    }
    allocations = [0] * len(candidates)
    for component_indices in _candidate_components(candidates):
        component = [candidates[index] for index in component_indices]
        component_units = _solve_component(component, capacities)
        for index, units in zip(component_indices, component_units):
            allocations[index] = units

    consumed: dict[str, int] = defaultdict(int)
    for candidate, units in zip(candidates, allocations):
        if units == 0:
            continue
        credit = candidate.credit(units)
        legs = candidate.row["legs"]
        number_of_legs = len(legs)
        ordinary_share = q2(credit / number_of_legs)
        for leg_index, leg in enumerate(legs):
            share = (
                ordinary_share
                if leg_index < number_of_legs - 1
                else credit - ordinary_share * (number_of_legs - 1)
            )
            commodities[leg["cc"]].inter_credit += share
        for cc_id, ratio in candidate.consumption:
            consumed[cc_id] += units * ratio

    for cc_id, commodity in commodities.items():
        commodity.inter_credit = q2(commodity.inter_credit)
        used = consumed[cc_id]
        sign = 1.0 if commodity.outright_delta > 0.0 else -1.0
        commodity.residual_delta = sign * (abs(commodity.outright_delta) - used)
        if commodity.residual_delta == -0.0:
            commodity.residual_delta = 0.0


def _option_overlays(commodity: Commodity) -> None:
    som_total = 0.0
    nov_total = 0.0
    lao_total = 0.0
    for position in commodity.positions:
        if not position.is_option:
            continue
        quantity = position.qty
        absolute_delta = abs(position.atm_delta)
        if quantity < 0.0:
            som_total += (
                float(position.product["som_rate"])
                * abs(quantity)
                * (1.0 + max(0.0, 0.25 - absolute_delta))
            )
            lao_total += (
                float(position.product["lao_rate"])
                * abs(quantity)
                * max(0.0, float(position.product["lao_otm"]) - absolute_delta)
            )
        elif quantity > 0.0 and absolute_delta < 0.35:
            nov_total += max(
                0.0,
                quantity * position.base_value * float(position.product["multiplier"]),
            )

    commodity.som = q2(som_total)
    uncapped_nov = q2(nov_total)
    commodity.nov_credit = q2(min(uncapped_nov, commodity.scanning_risk))
    commodity.liquidity_addon = q2(lao_total)


def _commodity_primary_product(
    cc_id: str, product_names: list[str], products: dict
) -> tuple[list[str], dict]:
    ordered_names = [name for name in products if name in product_names]
    configs = [products[name] for name in ordered_names]
    currencies = {product["currency"] for product in configs}
    groups = {product["ics_group"] for product in configs}
    if len(currencies) != 1 or len(groups) != 1:
        raise ValueError(f"products in {cc_id} must share currency and ics_group")
    return ordered_names, configs[0]


def compute_report(portfolio: dict, market: dict, config: dict) -> dict:
    net = net_positions(portfolio)
    products = config["products"]
    valuation_date = date.fromisoformat(market["valuation_date"])
    house = config["house"]

    positions_by_cc: dict[str, list[Position]] = defaultdict(list)
    names_by_cc: dict[str, set[str]] = defaultdict(set)
    # Net positions are a book, not a blotter sequence. Lexical traversal keeps
    # all later binary64 summations invariant to journal operation order.
    for instrument_id, quantity in sorted(net.items()):
        product_name = _parse_instrument(instrument_id)[0]
        position = _make_position(
            instrument_id,
            quantity,
            products,
            market,
            house,
            valuation_date,
        )
        cc_id = position.product["cc_id"]
        positions_by_cc[cc_id].append(position)
        names_by_cc[cc_id].add(product_name)

    commodities: dict[str, Commodity] = {}
    for cc_id, positions in positions_by_cc.items():
        names, primary = _commodity_primary_product(
            cc_id, list(names_by_cc[cc_id]), products
        )
        commodity = Commodity(
            cc_id=cc_id,
            product_names=names,
            positions=positions,
            product=primary,
            currency=primary["currency"],
            ics_group=primary["ics_group"],
        )
        _scan_and_deltas(commodity)
        _intra_spread(commodity)
        _strip_credit(commodity)
        commodities[cc_id] = commodity

    _inter_spreads(commodities, config["inter_spreads"])

    fx = {currency: _decimal(value) for currency, value in market["fx_to_usd"].items()}
    report_rows: list[dict[str, Any]] = []
    total_margin = ZERO
    for cc_id in sorted(commodities):
        commodity = commodities[cc_id]
        _option_overlays(commodity)
        threshold = float(commodity.product["concentration_threshold"])
        excess = max(0.0, abs(commodity.residual_delta) - threshold)
        commodity.concentration_charge = q2(
            excess * float(commodity.product["concentration_rate"])
        )

        raw_margin = q2(
            commodity.scanning_risk
            + commodity.intra_charge
            + commodity.concentration_charge
            - commodity.inter_credit
            - commodity.nov_credit
            - commodity.strip_credit
        )
        native_before_liquidity = max(raw_margin, commodity.som)
        native_margin = q2(native_before_liquidity + commodity.liquidity_addon)
        usd_margin = q2(native_margin * fx[commodity.currency])
        total_margin += usd_margin
        report_rows.append(
            {
                "cc_id": cc_id,
                "currency": commodity.currency,
                "scanning_risk": commodity.scanning_risk,
                "intra_charge": commodity.intra_charge,
                "inter_credit": commodity.inter_credit,
                "nov_credit": commodity.nov_credit,
                "som": commodity.som,
                "strip_credit": commodity.strip_credit,
                "concentration_charge": commodity.concentration_charge,
                "liquidity_addon": commodity.liquidity_addon,
                "raw_margin": raw_margin,
                "cc_margin_native": native_margin,
                "cc_margin_usd": usd_margin,
                "worst_scenario_id": commodity.worst_scenario_id,
            }
        )

    return {
        "valuation_date": market["valuation_date"],
        "currency": "USD",
        "total_margin_usd": q2(total_margin),
        "combined_commodities": report_rows,
    }


def load_json(path: str | Path) -> dict[str, Any]:
    # Preserve decimal config rates and FX exactly; valuation paths explicitly
    # convert the inputs that the methodology requires to be binary64.
    return json.loads(Path(path).read_text(), parse_float=Decimal)


def _json_ready(value: Any, key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {child_key: _json_ready(child, child_key) for child_key, child in value.items()}
    if isinstance(value, list):
        return [_json_ready(child) for child in value]
    if isinstance(value, Decimal):
        if key in _MONEY_FIELDS:
            return f"__HSM_MONEY__{q2(value):.2f}"
        return float(value)
    return value


def write_report(report: dict, path: str | Path) -> None:
    """Write schema money fields as JSON numbers with exactly two decimals."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(_json_ready(report), indent=2)
    rendered = re.sub(r'"__HSM_MONEY__(-?\d+\.\d{2})"', r"\1", rendered)
    output_path.write_text(rendered + "\n")
