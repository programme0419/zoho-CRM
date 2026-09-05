"""House Scan Margin calculation engine.

The calculation in this module follows ``docs/methodology.md``.  In
particular, scenario P/L is rounded at the position/scenario boundary; the
remaining monetary amounts are rounded only at the points called out by the
methodology.
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

try:  # Support both ``python hsm/run_margin.py`` and package imports.
    from .lib import black76
except ImportError:  # pragma: no cover - exercised by the CLI entry point
    from lib import black76


CENT = Decimal("0.01")
ZERO = Decimal("0.00")

# (price multiplier, direction of the volatility shock, P/L weight)
SCENARIOS: tuple[tuple[float, int, float], ...] = (
    (0.0, +1, 1.0),
    (0.0, -1, 1.0),
    (1.0 / 3.0, +1, 1.0),
    (1.0 / 3.0, -1, 1.0),
    (-1.0 / 3.0, +1, 1.0),
    (-1.0 / 3.0, -1, 1.0),
    (2.0 / 3.0, +1, 1.0),
    (2.0 / 3.0, -1, 1.0),
    (-2.0 / 3.0, +1, 1.0),
    (-2.0 / 3.0, -1, 1.0),
    (1.0, +1, 1.0),
    (1.0, -1, 1.0),
    (-1.0, +1, 1.0),
    (-1.0, -1, 1.0),
    (3.0, +1, 0.28),
    (-3.0, -1, 0.28),
)

_OPTION_RE = re.compile(
    r"^(?P<product>.+)-(?P<year>\d{4})-(?P<month>\d{2})-"
    r"(?P<put_call>[CP])-(?P<strike>-?[^-]+)$"
)
_FUTURE_RE = re.compile(r"^(?P<product>.+)-(?P<year>\d{4})-(?P<month>\d{2})$")


def _decimal(value: Any) -> Decimal:
    """Convert user/config or binary64 output through its decimal spelling."""

    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def q2(value: Any) -> Decimal:
    """Round a monetary value to cents using round-half-to-even."""

    result = _decimal(value).quantize(CENT, rounding=ROUND_HALF_EVEN)
    # Do not expose negative zero in a report.
    return ZERO if result == 0 else result


def scenario_money(value: float) -> Decimal:
    """Apply the methodology's binary64 -> 10 decimals -> cents boundary."""

    return q2(Decimal(format(float(value), ".10f")))


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
    def bucket(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    @property
    def underlying_id(self) -> str:
        return f"{self.product}-{self.bucket}"

    @property
    def month_date(self) -> date:
        return date(self.year, self.month, 1)


@dataclass
class PositionResult:
    instrument: Instrument
    qty: float
    product_config: dict[str, Any]
    scenario_pl: list[Decimal]
    scenario_delta: list[float]
    atm_delta: float
    base_option_value: float


def parse_instrument(instrument_id: str) -> Instrument:
    """Parse an HSM future or option identifier, allowing '-' in products."""

    option_match = _OPTION_RE.fullmatch(instrument_id)
    if option_match:
        fields = option_match.groupdict()
        try:
            strike = float(fields["strike"])
            # This also validates the calendar month.
            date(int(fields["year"]), int(fields["month"]), 1)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid option instrument_id: {instrument_id}") from exc
        return Instrument(
            instrument_id=instrument_id,
            product=fields["product"],
            year=int(fields["year"]),
            month=int(fields["month"]),
            put_call=fields["put_call"],
            strike=strike,
        )

    future_match = _FUTURE_RE.fullmatch(instrument_id)
    if future_match:
        fields = future_match.groupdict()
        try:
            date(int(fields["year"]), int(fields["month"]), 1)
        except ValueError as exc:
            raise ValueError(f"invalid futures instrument_id: {instrument_id}") from exc
        return Instrument(
            instrument_id=instrument_id,
            product=fields["product"],
            year=int(fields["year"]),
            month=int(fields["month"]),
        )

    raise ValueError(f"invalid instrument_id: {instrument_id}")


def net_positions(portfolio: dict[str, Any]) -> dict[str, float]:
    """Net identical instruments and omit exact zero positions."""

    grouped: dict[str, list[float]] = defaultdict(list)
    for row in portfolio["positions"]:
        grouped[row["instrument_id"]].append(float(row["qty"]))
    quantities = {
        instrument_id: math.fsum(parts)
        for instrument_id, parts in grouped.items()
    }
    return {instrument_id: qty for instrument_id, qty in quantities.items() if qty != 0.0}


def product_of(instrument_id: str) -> str:
    """Compatibility helper returning the parsed product name."""

    return parse_instrument(instrument_id).product


def is_option(instrument_id: str) -> bool:
    """Compatibility helper identifying an option instrument."""

    return parse_instrument(instrument_id).is_option


def _effective_psr(
    instrument: Instrument,
    forward: float,
    valuation_date: date,
    product_config: dict[str, Any],
    house_config: dict[str, Any],
) -> float:
    delivery_days = (instrument.month_date - valuation_date).days
    if delivery_days <= int(house_config["delivery_scale_days"]):
        scale = 1.0
    else:
        scale = max(
            math.sqrt(delivery_days / 365.0),
            float(house_config["delivery_scale_floor"]),
        )
    return float(product_config["price_scan_range"]) * scale


def _shocked_forward(forward: float, price_mult: float, psr: float, shock_mode: str) -> float:
    if shock_mode == "linear":
        shocked = forward + price_mult * psr
    elif shock_mode == "log":
        shocked = forward * math.exp(price_mult * psr / forward) if forward > 0.0 else 1e-8
    else:
        raise ValueError(f"unsupported shock_mode: {shock_mode}")
    return max(shocked, 1e-8)


def _value_position(
    instrument: Instrument,
    qty: float,
    product_config: dict[str, Any],
    market: dict[str, Any],
    valuation_date: date,
    house_config: dict[str, Any],
) -> PositionResult:
    forward = float(market["futures_price"][instrument.underlying_id])
    multiplier = float(product_config["multiplier"])
    effective_psr = _effective_psr(
        instrument, forward, valuation_date, product_config, house_config
    )

    if instrument.is_option:
        vol = float(market["atm_vol"][instrument.instrument_id])
        expiry = date.fromisoformat(market["option_expiry"][instrument.instrument_id])
        time_to_expiry = black76.year_fraction(valuation_date, expiry)
        strike = float(instrument.strike)
        call = instrument.put_call == "C"
        base_value = black76.price(forward, strike, vol, time_to_expiry, call)
        atm_delta = black76.delta(forward, strike, vol, time_to_expiry, call)
    else:
        vol = 0.0
        time_to_expiry = 0.0
        strike = 0.0
        call = False
        base_value = 0.0
        atm_delta = 1.0

    scenario_pl: list[Decimal] = []
    scenario_delta: list[float] = []
    for price_mult, vol_direction, weight in SCENARIOS:
        shocked_forward = _shocked_forward(
            forward, price_mult, effective_psr, product_config["shock_mode"]
        )
        if instrument.is_option:
            fraction = (
                float(product_config["vol_scan_fraction"])
                if vol_direction > 0
                else float(product_config["vsf_down"])
            )
            shocked_vol = max(vol * (1.0 + vol_direction * fraction), 1e-6)
            shocked_value = black76.price(
                shocked_forward, strike, shocked_vol, time_to_expiry, call
            )
            raw_pl = qty * (shocked_value - base_value) * multiplier * weight
            per_contract_delta = black76.delta(
                shocked_forward, strike, shocked_vol, time_to_expiry, call
            )
        else:
            raw_pl = qty * (shocked_forward - forward) * multiplier * weight
            per_contract_delta = 1.0

        scenario_pl.append(scenario_money(raw_pl))
        scenario_delta.append(per_contract_delta)

    return PositionResult(
        instrument=instrument,
        qty=qty,
        product_config=product_config,
        scenario_pl=scenario_pl,
        scenario_delta=scenario_delta,
        atm_delta=atm_delta,
        base_option_value=base_value,
    )


def _composite_buckets(
    positions: list[PositionResult], cc_pl: list[Decimal], worst_scenario_id: int
) -> dict[str, float]:
    if worst_scenario_id <= 14:
        candidates = [
            scenario_id
            for scenario_id in range(1, 15)
            if scenario_id != worst_scenario_id
        ]
        next_worst = min(candidates, key=lambda scenario_id: (cc_pl[scenario_id - 1], scenario_id))
    else:
        next_worst = None

    buckets: dict[str, float] = defaultdict(float)
    for position in positions:
        delta = position.scenario_delta[worst_scenario_id - 1]
        if next_worst is not None:
            delta = (delta + position.scenario_delta[next_worst - 1]) / 2.0
        buckets[position.instrument.bucket] += position.qty * delta
    return dict(buckets)


def _month_distance(left: str, right: str) -> int:
    left_date = date(int(left[:4]), int(left[5:]), 1)
    right_date = date(int(right[:4]), int(right[5:]), 1)
    return abs((left_date - right_date).days)


def _intra_spread(
    buckets: dict[str, float], product_config: dict[str, Any]
) -> tuple[Decimal, dict[str, float]]:
    remaining = dict(buckets)
    charges: list[float] = []

    while True:
        active = [bucket for bucket, delta in remaining.items() if delta != 0.0]
        if not active:
            break
        bucket_a = min(active, key=lambda bucket: (-abs(remaining[bucket]), bucket))
        delta_a = remaining[bucket_a]
        opposites = [
            bucket
            for bucket in active
            if remaining[bucket] * delta_a < 0.0
        ]
        if not opposites:
            break

        bucket_b = min(
            opposites,
            key=lambda bucket: (
                _month_distance(bucket_a, bucket),
                -abs(remaining[bucket]),
                bucket,
            ),
        )
        delta_b = remaining[bucket_b]
        matched = min(abs(delta_a), abs(delta_b))
        distance = _month_distance(bucket_a, bucket_b)
        tiers = product_config["intra_tiers"]
        if distance <= 32:
            rate = float(tiers["adjacent"])
        elif distance <= 125:
            rate = float(tiers["mid"])
        else:
            rate = float(tiers["back"])
        charges.append(matched * rate * math.sqrt(distance / 365.0))

        remaining[bucket_a] = math.copysign(abs(delta_a) - matched, delta_a)
        remaining[bucket_b] = math.copysign(abs(delta_b) - matched, delta_b)
        if remaining[bucket_a] == 0.0:
            remaining[bucket_a] = 0.0
        if remaining[bucket_b] == 0.0:
            remaining[bucket_b] = 0.0

    return q2(sum(charges)), remaining


def _month_number(bucket: str) -> int:
    return int(bucket[:4]) * 12 + int(bucket[5:]) - 1


def _strip_credit(remaining: dict[str, float], strip_rate: float) -> Decimal:
    if strip_rate == 0.0:
        return ZERO

    months = sorted(bucket for bucket, delta in remaining.items() if delta != 0.0)
    runs: list[list[str]] = []
    for bucket in months:
        if not runs or _month_number(bucket) != _month_number(runs[-1][-1]) + 1:
            runs.append([bucket])
        else:
            runs[-1].append(bucket)

    credit = 0.0
    for run in runs:
        if len(run) >= 3:
            credit += (
                (len(run) - 2)
                * strip_rate
                * min(abs(remaining[bucket]) for bucket in run)
            )
    return q2(credit)


def _cc_metadata(products: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build CC metadata and reject otherwise-ambiguous mixed definitions."""

    result: dict[str, dict[str, Any]] = {}
    for product_name, product in products.items():
        cc_id = product["cc_id"]
        if cc_id in result:
            old = result[cc_id]
            for field in ("currency", "ics_group"):
                if old[field] != product[field]:
                    raise ValueError(
                        f"products in {cc_id} have inconsistent {field}: "
                        f"{old[field]} and {product[field]}"
                    )
        else:
            result[cc_id] = {
                "currency": product["currency"],
                "ics_group": product["ics_group"],
                "product_name": product_name,
                "product_config": product,
            }
    return result


def _apply_inter_spreads(
    outright: dict[str, float],
    cc_meta: dict[str, dict[str, Any]],
    inter_spreads: list[dict[str, Any]],
) -> tuple[dict[str, Decimal], dict[str, float]]:
    credits = {cc_id: ZERO for cc_id in outright}
    residual = dict(outright)

    for spread in sorted(inter_spreads, key=lambda row: int(row["priority"])):
        leg_a = spread["leg_a"]
        leg_b = spread["leg_b"]
        if leg_a == leg_b or leg_a not in cc_meta or leg_b not in cc_meta:
            continue
        meta_a = cc_meta[leg_a]
        meta_b = cc_meta[leg_b]
        if (
            meta_a["ics_group"] != meta_b["ics_group"]
            or meta_a["ics_group"] != spread["ics_group"]
            or meta_a["currency"] != meta_b["currency"]
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

        # Set an exhausted leg to exact zero.  Reconstructing it through a
        # divide/multiply pair can otherwise leave a binary64 dust residual,
        # which must not feed a later spread or the concentration overlay.
        residual[leg_a] = (
            0.0
            if paired == abs(units_a)
            else delta_a - math.copysign(paired * ratio_a, delta_a)
        )
        residual[leg_b] = (
            0.0
            if paired == abs(units_b)
            else delta_b - math.copysign(paired * ratio_b, delta_b)
        )

    return credits, residual


def _option_amounts(
    positions: list[PositionResult], scanning_risk: Decimal
) -> tuple[Decimal, Decimal, Decimal]:
    som_total = 0.0
    nov_total = 0.0
    liquidity_total = 0.0
    for position in positions:
        if not position.instrument.is_option:
            continue
        qty = position.qty
        product = position.product_config
        absolute_delta = abs(position.atm_delta)
        if qty < 0.0:
            som_total += (
                float(product["som_rate"])
                * abs(qty)
                * (1.0 + max(0.0, 0.25 - absolute_delta))
            )
            liquidity_total += (
                float(product["lao_rate"])
                * abs(qty)
                * max(0.0, float(product["lao_otm"]) - absolute_delta)
            )
        elif qty > 0.0 and absolute_delta < 0.35:
            nov_total += max(
                0.0,
                qty
                * position.base_option_value
                * float(product["multiplier"]),
            )

    som = q2(som_total)
    nov = q2(min(_decimal(nov_total), scanning_risk))
    liquidity = q2(liquidity_total)
    return som, nov, liquidity


def compute_report(
    portfolio: dict[str, Any], market: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    """Compute a complete HSM margin report from the three input objects."""

    products: dict[str, dict[str, Any]] = config["products"]
    cc_meta = _cc_metadata(products)
    valuation_date = date.fromisoformat(market["valuation_date"])
    net = net_positions(portfolio)

    positions_by_cc: dict[str, list[PositionResult]] = defaultdict(list)
    for instrument_id, qty in sorted(net.items()):
        instrument = parse_instrument(instrument_id)
        product = products[instrument.product]
        position = _value_position(
            instrument,
            qty,
            product,
            market,
            valuation_date,
            config["house"],
        )
        positions_by_cc[product["cc_id"]].append(position)

    # Core scan, composite delta, intra charge, and pre-ICS strip credit.
    preliminary: dict[str, dict[str, Any]] = {}
    outright: dict[str, float] = {}
    for cc_id, positions in positions_by_cc.items():
        cc_pl = [
            sum((position.scenario_pl[index] for position in positions), ZERO)
            for index in range(16)
        ]
        worst_index = min(range(16), key=lambda index: (cc_pl[index], index + 1))
        worst_scenario_id = worst_index + 1
        scanning_risk = q2(max(Decimal(0), -cc_pl[worst_index]))
        buckets = _composite_buckets(positions, cc_pl, worst_scenario_id)

        # Intra/strip/concentration parameters are CC-level in the methodology.
        cc_product = cc_meta[cc_id]["product_config"]
        intra_charge, remaining = _intra_spread(buckets, cc_product)
        strip_credit = _strip_credit(remaining, float(cc_product["strip_rate"]))
        outright[cc_id] = sum(remaining.values())
        preliminary[cc_id] = {
            "positions": positions,
            "scanning_risk": scanning_risk,
            "intra_charge": intra_charge,
            "strip_credit": strip_credit,
            "worst_scenario_id": worst_scenario_id,
        }

    # Priority-ordered ICS consumes outright delta.  Concentration uses the
    # residual left by this pass.
    inter_credit, residual = _apply_inter_spreads(
        outright, cc_meta, config["inter_spreads"]
    )

    fx = {currency: _decimal(rate) for currency, rate in market["fx_to_usd"].items()}
    rows: list[dict[str, Any]] = []
    total = ZERO
    for cc_id in sorted(positions_by_cc):
        values = preliminary[cc_id]
        product = cc_meta[cc_id]["product_config"]
        scanning_risk = values["scanning_risk"]
        som, nov_credit, liquidity_addon = _option_amounts(
            values["positions"], scanning_risk
        )

        residual_delta = abs(residual.get(cc_id, outright[cc_id]))
        threshold = float(product["concentration_threshold"])
        concentration_charge = q2(
            max(0.0, residual_delta - threshold)
            * float(product["concentration_rate"])
        )
        raw_margin = q2(
            scanning_risk
            + values["intra_charge"]
            + concentration_charge
            - inter_credit[cc_id]
            - nov_credit
            - values["strip_credit"]
        )
        cc_margin_native = q2(max(raw_margin, som) + liquidity_addon)
        currency = cc_meta[cc_id]["currency"]
        cc_margin_usd = q2(cc_margin_native * fx[currency])
        total += cc_margin_usd

        rows.append(
            {
                "cc_id": cc_id,
                "currency": currency,
                "scanning_risk": scanning_risk,
                "intra_charge": values["intra_charge"],
                "inter_credit": inter_credit[cc_id],
                "nov_credit": nov_credit,
                "som": som,
                "strip_credit": values["strip_credit"],
                "concentration_charge": concentration_charge,
                "liquidity_addon": liquidity_addon,
                "raw_margin": raw_margin,
                "cc_margin_native": cc_margin_native,
                "cc_margin_usd": cc_margin_usd,
                "worst_scenario_id": values["worst_scenario_id"],
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
_MONEY_MARKER = "__HSM_FIXED_2_DECIMALS__"


def _money_for_json(value: Any) -> str:
    return f"{q2(value):.2f}"


def write_report(report: dict[str, Any], path: str | Path) -> None:
    """Write the report, retaining two decimal places on JSON money numbers."""

    def mark_money(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: (
                    _MONEY_MARKER + _money_for_json(item)
                    if key in _MONEY_FIELDS
                    else mark_money(item)
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [mark_money(item) for item in value]
        return value

    rendered = json.dumps(mark_money(report), indent=2)
    rendered = re.sub(
        rf'"{re.escape(_MONEY_MARKER)}(-?\d+\.\d{{2}})"',
        r"\1",
        rendered,
    )
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered + "\n")
