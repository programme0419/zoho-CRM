"""House Scan Margin engine.

The calculation in this module follows ``docs/methodology.md``. In
particular, scenario P/L is rounded per net position before it is combined,
while the house overlays are applied only after the core scan and spreading.
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

try:  # Support both ``import hsm.engine`` and the standalone CLI.
    from .lib.black76 import delta as black_delta
    from .lib.black76 import price as black_price
    from .lib.black76 import year_fraction
except ImportError:  # pragma: no cover - exercised by run_margin.py
    from lib.black76 import delta as black_delta
    from lib.black76 import price as black_price
    from lib.black76 import year_fraction


CENT = Decimal("0.01")

# (price multiplier, vol direction, P/L weight), in scenario-id order.
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

_INSTRUMENT_RE = re.compile(
    r"^(?P<product>.+)-(?P<year>\d{4})-(?P<month>\d{2})"
    r"(?:-(?P<option_type>[CP])-(?P<strike>\d+\.\d{2}))?$"
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


def q2(value: Decimal | int | float | str) -> Decimal:
    """Round a monetary value to cents using round-half-to-even."""

    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    result = value.quantize(CENT, rounding=ROUND_HALF_EVEN)
    # Do not emit or propagate a cosmetic negative zero.
    return Decimal("0.00") if result == 0 else result


def scenario_money(value: float) -> Decimal:
    """Apply the methodology's binary64 -> 10 decimals -> cents boundary."""

    return Decimal(format(float(value), ".10f")).quantize(
        CENT, rounding=ROUND_HALF_EVEN
    )


@dataclass(frozen=True)
class Position:
    instrument_id: str
    product: str
    month: str
    qty: float
    config: dict[str, Any]
    forward: float
    psr: float
    option_type: str | None = None
    strike: float = 0.0
    vol: float = 0.0
    time_to_expiry: float = 0.0

    @property
    def is_option(self) -> bool:
        return self.option_type is not None

    @property
    def multiplier(self) -> float:
        return float(self.config["multiplier"])

    @property
    def is_call(self) -> bool:
        return self.option_type == "C"

    def shocked_inputs(self, scenario_index: int) -> tuple[float, float]:
        price_mult, vol_direction, _ = SCENARIOS[scenario_index]
        if self.config["shock_mode"] == "linear":
            shocked_forward = self.forward + price_mult * self.psr
        elif self.forward > 0.0:
            shocked_forward = self.forward * math.exp(
                price_mult * self.psr / self.forward
            )
        else:
            shocked_forward = 1.0e-8
        shocked_forward = max(shocked_forward, 1.0e-8)

        fraction = (
            float(self.config["vol_scan_fraction"])
            if vol_direction > 0
            else -float(self.config["vsf_down"])
        )
        shocked_vol = max(self.vol * (1.0 + fraction), 1.0e-6)
        return shocked_forward, shocked_vol

    def scenario_pl(self, scenario_index: int) -> float:
        shocked_forward, shocked_vol = self.shocked_inputs(scenario_index)
        weight = SCENARIOS[scenario_index][2]
        if not self.is_option:
            return (
                self.qty
                * (shocked_forward - self.forward)
                * self.multiplier
                * weight
            )

        base_value = black_price(
            self.forward,
            self.strike,
            self.vol,
            self.time_to_expiry,
            self.is_call,
        )
        shocked_value = black_price(
            shocked_forward,
            self.strike,
            shocked_vol,
            self.time_to_expiry,
            self.is_call,
        )
        return (
            self.qty
            * (shocked_value - base_value)
            * self.multiplier
            * weight
        )

    def scenario_delta(self, scenario_index: int) -> float:
        if not self.is_option:
            return 1.0
        shocked_forward, shocked_vol = self.shocked_inputs(scenario_index)
        return black_delta(
            shocked_forward,
            self.strike,
            shocked_vol,
            self.time_to_expiry,
            self.is_call,
        )

    def atm_delta(self) -> float:
        if not self.is_option:
            return 1.0
        return black_delta(
            self.forward,
            self.strike,
            self.vol,
            self.time_to_expiry,
            self.is_call,
        )

    def base_option_value(self) -> float:
        if not self.is_option:
            return 0.0
        return black_price(
            self.forward,
            self.strike,
            self.vol,
            self.time_to_expiry,
            self.is_call,
        )


def _parse_instrument(instrument_id: str) -> tuple[str, str, str | None, float]:
    match = _INSTRUMENT_RE.fullmatch(instrument_id)
    if match is None:
        raise ValueError(f"invalid instrument_id: {instrument_id!r}")
    product = match.group("product")
    year = int(match.group("year"))
    month_number = int(match.group("month"))
    # This validates the calendar month as well as producing its canonical key.
    date(year, month_number, 1)
    month = f"{year:04d}-{month_number:02d}"
    option_type = match.group("option_type")
    strike = float(match.group("strike")) if option_type is not None else 0.0
    return product, month, option_type, strike


def _net_positions(portfolio: dict[str, Any]) -> dict[str, Decimal]:
    # Decimal netting makes decimal quantities which mathematically cancel truly
    # disappear before any binary64 valuation is performed.
    quantities: dict[str, Decimal] = defaultdict(Decimal)
    for row in portfolio["positions"]:
        quantities[row["instrument_id"]] += Decimal(str(row["qty"]))
    return {iid: qty for iid, qty in quantities.items() if qty != 0}


def _build_positions(
    portfolio: dict[str, Any], market: dict[str, Any], config: dict[str, Any]
) -> list[Position]:
    valuation_date = date.fromisoformat(market["valuation_date"])
    house = config["house"]
    positions: list[Position] = []

    for instrument_id, decimal_qty in sorted(_net_positions(portfolio).items()):
        product, month, option_type, strike = _parse_instrument(instrument_id)
        product_config = config["products"][product]
        underlying_id = f"{product}-{month}"
        forward = float(market["futures_price"][underlying_id])

        year, month_number = (int(part) for part in month.split("-"))
        delivery_days = (date(year, month_number, 1) - valuation_date).days
        if delivery_days <= int(house["delivery_scale_days"]):
            delivery_scale = 1.0
        else:
            delivery_scale = max(
                math.sqrt(delivery_days / 365.0),
                float(house["delivery_scale_floor"]),
            )
        effective_psr = float(product_config["price_scan_range"]) * delivery_scale

        vol = 0.0
        time_to_expiry = 0.0
        if option_type is not None:
            vol = float(market["atm_vol"][instrument_id])
            expiry = date.fromisoformat(market["option_expiry"][instrument_id])
            time_to_expiry = year_fraction(valuation_date, expiry)

        positions.append(
            Position(
                instrument_id=instrument_id,
                product=product,
                month=month,
                qty=float(decimal_qty),
                config=product_config,
                forward=forward,
                psr=effective_psr,
                option_type=option_type,
                strike=strike,
                vol=vol,
                time_to_expiry=time_to_expiry,
            )
        )
    return positions


def _month_start(month: str) -> date:
    year, month_number = (int(part) for part in month.split("-"))
    return date(year, month_number, 1)


def _month_ordinal(month: str) -> int:
    year, month_number = (int(part) for part in month.split("-"))
    return year * 12 + month_number - 1


def _toward_zero(value: float, amount: float) -> float:
    if abs(value) <= amount:
        return 0.0
    return value - math.copysign(amount, value)


def _intra_spread(
    bucket_deltas: dict[str, float], product_config: dict[str, Any]
) -> tuple[Decimal, dict[str, float]]:
    remaining = dict(bucket_deltas)
    charges: list[float] = []
    tiers = product_config["intra_tiers"]

    while any(value > 0.0 for value in remaining.values()) and any(
        value < 0.0 for value in remaining.values()
    ):
        nonzero = [month for month, value in remaining.items() if value != 0.0]
        leg_a = min(nonzero, key=lambda month: (-abs(remaining[month]), month))
        a_value = remaining[leg_a]
        opposites = [
            month
            for month, value in remaining.items()
            if value != 0.0 and value * a_value < 0.0
        ]
        a_date = _month_start(leg_a)
        leg_b = min(
            opposites,
            key=lambda month: (
                abs((_month_start(month) - a_date).days),
                -abs(remaining[month]),
                month,
            ),
        )

        quantity = min(abs(a_value), abs(remaining[leg_b]))
        remaining[leg_a] = _toward_zero(a_value, quantity)
        remaining[leg_b] = _toward_zero(remaining[leg_b], quantity)

        days = abs((_month_start(leg_b) - a_date).days)
        if days <= 32:
            rate = float(tiers["adjacent"])
        elif days <= 125:
            rate = float(tiers["mid"])
        else:
            rate = float(tiers["back"])
        charges.append(quantity * rate * math.sqrt(days / 365.0))

    return q2(Decimal(str(sum(charges)))), remaining


def _strip_credit(
    remaining: dict[str, float], product_config: dict[str, Any]
) -> Decimal:
    rate = float(product_config["strip_rate"])
    if rate == 0.0:
        return Decimal("0.00")

    months = sorted(month for month, value in remaining.items() if value != 0.0)
    runs: list[list[str]] = []
    for month in months:
        if not runs or _month_ordinal(month) != _month_ordinal(runs[-1][-1]) + 1:
            runs.append([month])
        else:
            runs[-1].append(month)

    credit = 0.0
    for run in runs:
        if len(run) >= 3:
            credit += (
                (len(run) - 2)
                * rate
                * min(abs(remaining[month]) for month in run)
            )
    return q2(Decimal(str(credit)))


def _cc_configuration(
    config: dict[str, Any], cc_id: str
) -> tuple[str, dict[str, Any]]:
    matches = sorted(
        (product, product_config)
        for product, product_config in config["products"].items()
        if product_config["cc_id"] == cc_id
    )
    if not matches:
        raise KeyError(f"unknown combined commodity {cc_id!r}")
    return matches[0]


def _valid_inter_pair(
    spread: dict[str, Any], config: dict[str, Any]
) -> bool:
    leg_configs: list[list[dict[str, Any]]] = []
    for leg_name in ("leg_a", "leg_b"):
        cc_id = spread[leg_name]
        configs = [
            product_config
            for product_config in config["products"].values()
            if product_config["cc_id"] == cc_id
        ]
        if not configs:
            return False
        leg_configs.append(configs)

    all_configs = leg_configs[0] + leg_configs[1]
    currencies = {product_config["currency"] for product_config in all_configs}
    return len(currencies) == 1 and all(
        product_config["ics_group"] == spread["ics_group"]
        for product_config in all_configs
    )


def _apply_inter_spreads(
    outright: dict[str, float], config: dict[str, Any]
) -> tuple[dict[str, Decimal], dict[str, float]]:
    credits: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    residual = dict(outright)

    for spread in sorted(config["inter_spreads"], key=lambda item: item["priority"]):
        if not _valid_inter_pair(spread, config):
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

        paired_units = min(abs(units_a), abs(units_b))
        total_credit = q2(
            Decimal(str(paired_units))
            * Decimal(str(spread["credit_per_unit"]))
            * (Decimal("1") - Decimal(str(spread["rho"])))
        )
        credit_b = q2(total_credit / 2)
        credit_a = total_credit - credit_b
        credits[leg_a] += credit_a
        credits[leg_b] += credit_b

        if abs(units_a) == paired_units:
            residual[leg_a] = 0.0
        else:
            residual[leg_a] = _toward_zero(delta_a, paired_units * ratio_a)
        if abs(units_b) == paired_units:
            residual[leg_b] = 0.0
        else:
            residual[leg_b] = _toward_zero(delta_b, paired_units * ratio_b)

    return dict(credits), residual


def compute_report(
    portfolio: dict[str, Any], market: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    positions = _build_positions(portfolio, market, config)
    by_cc: dict[str, list[Position]] = defaultdict(list)
    for position in positions:
        by_cc[position.config["cc_id"]].append(position)

    # Core scenario scan and composite deltas.
    core: dict[str, dict[str, Any]] = {}
    for cc_id in sorted(by_cc):
        cc_positions = by_cc[cc_id]
        scenario_pl: list[tuple[int, Decimal]] = []
        for scenario_index in range(16):
            combined_pl = sum(
                (
                    scenario_money(position.scenario_pl(scenario_index))
                    for position in cc_positions
                ),
                Decimal("0.00"),
            )
            scenario_pl.append((scenario_index + 1, combined_pl))

        worst_scenario_id, worst_pl = min(
            scenario_pl, key=lambda item: (item[1], item[0])
        )
        scanning_risk = q2(max(Decimal("0.00"), -worst_pl))
        if worst_scenario_id <= 14:
            second_scenario_id, _ = min(
                (
                    item
                    for item in scenario_pl
                    if item[0] <= 14 and item[0] != worst_scenario_id
                ),
                key=lambda item: (item[1], item[0]),
            )
        else:
            second_scenario_id = None

        bucket_deltas: dict[str, float] = defaultdict(float)
        for position in cc_positions:
            primary_delta = position.scenario_delta(worst_scenario_id - 1)
            if second_scenario_id is None:
                composite_per_contract = primary_delta
            else:
                secondary_delta = position.scenario_delta(second_scenario_id - 1)
                composite_per_contract = (primary_delta + secondary_delta) / 2.0
            bucket_deltas[position.month] += composite_per_contract * position.qty

        _, cc_config = _cc_configuration(config, cc_id)
        intra_charge, remaining = _intra_spread(dict(bucket_deltas), cc_config)
        strip_credit = _strip_credit(remaining, cc_config)
        outright = sum(remaining.values())
        core[cc_id] = {
            "positions": cc_positions,
            "scanning_risk": scanning_risk,
            "worst_scenario_id": worst_scenario_id,
            "intra_charge": intra_charge,
            "strip_credit": strip_credit,
            "outright": outright,
            "config": cc_config,
        }

    # ICS is portfolio-wide and priority-sensitive. Concentration follows it.
    inter_credits, residual = _apply_inter_spreads(
        {cc_id: values["outright"] for cc_id, values in core.items()}, config
    )

    rows: list[dict[str, Any]] = []
    total_margin_usd = Decimal("0.00")
    fx = {
        currency: Decimal(str(value))
        for currency, value in market["fx_to_usd"].items()
    }

    for cc_id in sorted(core):
        values = core[cc_id]
        cc_positions: list[Position] = values["positions"]
        cc_config = values["config"]
        currency = cc_config["currency"]

        som_unrounded = 0.0
        nov_unrounded = 0.0
        liquidity_unrounded = 0.0
        for position in cc_positions:
            if not position.is_option:
                continue
            atm_delta = position.atm_delta()
            if position.qty < 0.0:
                som_unrounded += (
                    float(position.config["som_rate"])
                    * abs(position.qty)
                    * (1.0 + max(0.0, 0.25 - abs(atm_delta)))
                )
                liquidity_unrounded += (
                    float(position.config["lao_rate"])
                    * abs(position.qty)
                    * max(
                        0.0,
                        float(position.config["lao_otm"]) - abs(atm_delta),
                    )
                )
            elif position.qty > 0.0 and abs(atm_delta) < 0.35:
                nov_unrounded += max(
                    0.0,
                    position.qty
                    * position.base_option_value()
                    * position.multiplier,
                )

        som = q2(Decimal(str(som_unrounded)))
        nov_credit = q2(
            min(Decimal(str(nov_unrounded)), values["scanning_risk"])
        )
        liquidity_addon = q2(Decimal(str(liquidity_unrounded)))
        inter_credit = inter_credits.get(cc_id, Decimal("0.00"))

        residual_delta = residual.get(cc_id, values["outright"])
        excess_delta = max(
            0.0,
            abs(residual_delta) - float(cc_config["concentration_threshold"]),
        )
        concentration_charge = q2(
            Decimal(str(excess_delta))
            * Decimal(str(cc_config["concentration_rate"]))
        )

        raw_margin = q2(
            values["scanning_risk"]
            + values["intra_charge"]
            + concentration_charge
            - inter_credit
            - nov_credit
            - values["strip_credit"]
        )
        cc_margin_native = max(raw_margin, som) + liquidity_addon
        cc_margin_usd = q2(cc_margin_native * fx[currency])
        total_margin_usd += cc_margin_usd

        rows.append(
            {
                "cc_id": cc_id,
                "currency": currency,
                "scanning_risk": float(values["scanning_risk"]),
                "intra_charge": float(values["intra_charge"]),
                "inter_credit": float(inter_credit),
                "nov_credit": float(nov_credit),
                "som": float(som),
                "strip_credit": float(values["strip_credit"]),
                "concentration_charge": float(concentration_charge),
                "liquidity_addon": float(liquidity_addon),
                "raw_margin": float(raw_margin),
                "cc_margin_native": float(cc_margin_native),
                "cc_margin_usd": float(cc_margin_usd),
                "worst_scenario_id": int(values["worst_scenario_id"]),
            }
        )

    return {
        "valuation_date": market["valuation_date"],
        "currency": "USD",
        "total_margin_usd": float(total_margin_usd),
        "combined_commodities": rows,
    }


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def _json_with_fixed_money(report: dict[str, Any]) -> str:
    """Serialize report money as JSON numbers with exactly two decimals."""

    def encode(value: Any, key: str | None = None, level: int = 0) -> str:
        if key in _MONEY_FIELDS:
            return format(q2(value), ".2f")
        if isinstance(value, dict):
            if not value:
                return "{}"
            child_indent = " " * (2 * (level + 1))
            items = [
                child_indent
                + json.dumps(item_key)
                + ": "
                + encode(item, item_key, level + 1)
                for item_key, item in value.items()
            ]
            return "{\n" + ",\n".join(items) + "\n" + " " * (2 * level) + "}"
        if isinstance(value, list):
            if not value:
                return "[]"
            child_indent = " " * (2 * (level + 1))
            items = [child_indent + encode(item, level=level + 1) for item in value]
            return "[\n" + ",\n".join(items) + "\n" + " " * (2 * level) + "]"
        return json.dumps(value, allow_nan=False)

    return encode(report) + "\n"


def write_report(report: dict[str, Any], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_json_with_fixed_money(report))
