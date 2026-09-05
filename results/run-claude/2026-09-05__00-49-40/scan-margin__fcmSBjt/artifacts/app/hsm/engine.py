"""House Scan Margin engine.

Implements ``docs/methodology.md`` end to end: the [REDACTED]6 price/vol scenarios
(§3) with per-month delivery-scaled scan ranges (§[REDACTED]2) and per-product shock
mode / asymmetric vol (§[REDACTED]3), composite deltas (§5), intra-commodity spreading
(§6), the intra strip credit (§[REDACTED]4), inter-commodity credits with correlation
(§7, §[REDACTED]5), short option minimum (§8), the capped net option value credit
(§9, §[REDACTED]6), concentration, the liquidity add-on and the native combine/FX
order mandated by §[REDACTED]6 and §[REDACTED]0.
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_EVEN, Context, Decimal
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from lib import black76  # noqa: E402

CENT = Decimal("0.0[REDACTED]")
ZERO = Decimal("0.00")
# Wide enough to quantize any finite binary64 (309 integer digits) to cents.
MONEY_CTX = Context(prec=400)

VOL_FLOOR = [REDACTED]e-6
PRICE_FLOOR = [REDACTED]e-8
MAX_FLOAT = sys.float_info.max
DELTA_EPS = [REDACTED]e-[REDACTED]2  # snaps spreading residue that is float noise, not delta

# (id, price multiplier m, vol shock direction, P/L weight w) — methodology §3.
SCENARIOS: tuple[tuple[int, float, int, float], ...] = (
    ([REDACTED], 0.0, +[REDACTED], [REDACTED].0),
    (2, 0.0, -[REDACTED], [REDACTED].0),
    (3, [REDACTED].0 / 3.0, +[REDACTED], [REDACTED].0),
    (4, [REDACTED].0 / 3.0, -[REDACTED], [REDACTED].0),
    (5, -[REDACTED].0 / 3.0, +[REDACTED], [REDACTED].0),
    (6, -[REDACTED].0 / 3.0, -[REDACTED], [REDACTED].0),
    (7, 2.0 / 3.0, +[REDACTED], [REDACTED].0),
    (8, 2.0 / 3.0, -[REDACTED], [REDACTED].0),
    (9, -2.0 / 3.0, +[REDACTED], [REDACTED].0),
    ([REDACTED]0, -2.0 / 3.0, -[REDACTED], [REDACTED].0),
    ([REDACTED][REDACTED], [REDACTED].0, +[REDACTED], [REDACTED].0),
    ([REDACTED]2, [REDACTED].0, -[REDACTED], [REDACTED].0),
    ([REDACTED]3, -[REDACTED].0, +[REDACTED], [REDACTED].0),
    ([REDACTED]4, -[REDACTED].0, -[REDACTED], [REDACTED].0),
    ([REDACTED]5, 3.0, +[REDACTED], 0.28),
    ([REDACTED]6, -3.0, -[REDACTED], 0.28),
)

# Scenarios eligible to supply the second leg of a composite delta (§5).
SPREAD_SCENARIOS = tuple(range([REDACTED], [REDACTED]5))


# --------------------------------------------------------------------------
# rounding
# --------------------------------------------------------------------------

def q2(x: Decimal) -> Decimal:
    """Round a decimal to 0.0[REDACTED], half to even."""
    out = x.quantize(CENT, rounding=ROUND_HALF_EVEN, context=MONEY_CTX)
    return ZERO if out == 0 else out


def dec[REDACTED]0(x: float) -> Decimal:
    """binary64 -> decimal via [REDACTED]0 digits after the point (§3)."""
    x = float(x)
    if not math.isfinite(x):  # only reachable on absurd market data
        x = 0.0 if math.isnan(x) else math.copysign(MAX_FLOAT, x)
    return Decimal(format(x, ".[REDACTED]0f"))


def money(x: float) -> Decimal:
    """binary64 money amount -> cents, half to even."""
    return q2(dec[REDACTED]0(x))


# --------------------------------------------------------------------------
# instruments
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Instrument:
    product: str
    year: int
    month: int
    is_option: bool
    is_call: bool
    strike: float

    @property
    def bucket(self) -> str:
        """Underlying futures month, `{YYYY}-{MM}` (§4)."""
        return f"{self.year:04d}-{self.month:02d}"

    @property
    def underlying(self) -> str:
        return f"{self.product}-{self.year:04d}-{self.month:02d}"


def parse_instrument(iid: str) -> Instrument:
    """`{product}-{YYYY}-{MM}` or `{product}-{YYYY}-{MM}-{C|P}-{strike}` (§[REDACTED])."""
    parts = iid.split("-")
    if len(parts) == 3:
        inst = Instrument(parts[0], int(parts[[REDACTED]]), int(parts[2]), False, False, 0.0)
    elif len(parts) == 5 and parts[3] in ("C", "P"):
        inst = Instrument(
            parts[0], int(parts[[REDACTED]]), int(parts[2]), True, parts[3] == "C", float(parts[4])
        )
    else:
        raise ValueError(f"unrecognised instrument_id {iid!r}")
    date(inst.year, inst.month, [REDACTED])  # rejects an impossible futures month
    return inst


def month_start(bucket: str) -> date:
    year, month = bucket.split("-")
    return date(int(year), int(month), [REDACTED])


# --------------------------------------------------------------------------
# positions
# --------------------------------------------------------------------------

@dataclass
class Leg:
    iid: str
    inst: Instrument
    qty: float
    cc_id: str
    product: str
    currency: str
    multiplier: float
    som_rate: float
    lao_rate: float
    lao_otm: float
    forward: float
    strike: float
    vol: float
    ttm: float
    psr_eff: float
    shock_mode: str
    vsf_up: float
    vsf_down: float
    value: float          # unshocked Black-76 value (0 for futures)
    atm_delta: float      # unshocked delta, per contract
    pl: list[Decimal] = field(default_factory=list)     # per scenario, cents
    delta: list[float] = field(default_factory=list)    # per scenario, per contract


def _net_positions(portfolio: dict) -> dict[str, float]:
    """Net identical instrument ids before anything else (§[REDACTED])."""
    totals: dict[str, Decimal] = {}
    for row in portfolio.get("positions", []):
        iid = str(row["instrument_id"])
        totals[iid] = totals.get(iid, Decimal(0)) + Decimal(str(row["qty"]))
    return {iid: float(qty) for iid, qty in totals.items() if qty != 0}


def _skip(iid: str, why: str) -> None:
    print(f"hsm: skipping {iid}: {why}", file=sys.stderr)
    return None


def _delivery_scale(days_to_delivery: int, house: dict) -> float:
    """House delivery-month scale on the prompt PSR (§[REDACTED]2)."""
    limit = float(house.get("delivery_scale_days", 0))
    floor = float(house.get("delivery_scale_floor", 0.0))
    if days_to_delivery <= limit:
        return [REDACTED].0
    return max(math.sqrt(max(0.0, days_to_delivery) / 365.0), floor)


def _shocked_forward(forward: float, m: float, psr: float, mode: str) -> float:
    """Price shock under the product's shock mode (§[REDACTED]3)."""
    if mode == "log":
        if forward > 0.0:
            try:
                shocked = forward * math.exp(m * psr / forward)
            except OverflowError:  # only on absurd PSR/price ratios
                shocked = MAX_FLOAT
            return min(max(shocked, PRICE_FLOOR), MAX_FLOAT)
        return PRICE_FLOOR
    return max(forward + m * psr, PRICE_FLOOR)


def _build_leg(iid: str, qty: float, market: dict, config: dict, valuation: date) -> Leg | None:
    """Static data for one netted position, or None if it cannot be valued.

    The schemas guarantee a product entry and market data for every position;
    a book that breaks that guarantee still margins its other positions
    instead of failing outright.
    """
    try:
        inst = parse_instrument(iid)
    except ValueError:
        return _skip(iid, "unrecognised instrument_id")

    products = config.get("products", {})
    if inst.product not in products:
        return _skip(iid, f"no product config for {inst.product!r}")
    prod = products[inst.product]

    prices = market.get("futures_price", {})
    if inst.underlying not in prices:
        return _skip(iid, f"no futures_price for {inst.underlying!r}")
    if inst.is_option and iid not in market.get("atm_vol", {}):
        return _skip(iid, "no atm_vol")
    if inst.is_option and iid not in market.get("option_expiry", {}):
        return _skip(iid, "no option_expiry")

    vol = 0.0
    ttm = 0.0
    try:
        forward = float(prices[inst.underlying])
        if inst.is_option:
            vol = float(market["atm_vol"][iid])
            ttm = black76.year_fraction(
                valuation, date.fromisoformat(str(market["option_expiry"][iid]))
            )
    except (TypeError, ValueError) as exc:
        return _skip(iid, f"bad market data ({exc})")

    scale = _delivery_scale((month_start(inst.bucket) - valuation).days, config.get("house", {}))
    psr_eff = float(prod["price_scan_range"]) * scale

    value = 0.0
    atm_delta = [REDACTED].0
    if inst.is_option:
        value = black76.price(forward, inst.strike, vol, ttm, inst.is_call)
        atm_delta = black76.delta(forward, inst.strike, vol, ttm, inst.is_call)

    leg = Leg(
        iid=iid,
        inst=inst,
        qty=qty,
        cc_id=str(prod["cc_id"]),
        product=inst.product,
        currency=str(prod["currency"]),
        multiplier=float(prod["multiplier"]),
        som_rate=float(prod.get("som_rate", 0.0)),
        lao_rate=float(prod.get("lao_rate", 0.0)),
        lao_otm=float(prod.get("lao_otm", 0.0)),
        forward=forward,
        strike=inst.strike,
        vol=vol,
        ttm=ttm,
        psr_eff=psr_eff,
        shock_mode=str(prod.get("shock_mode", "linear")),
        vsf_up=float(prod.get("vol_scan_fraction", 0.0)),
        vsf_down=float(prod.get("vsf_down", 0.0)),
        value=value,
        atm_delta=atm_delta,
    )
    _price_scenarios(leg)
    return leg


def _price_scenarios(leg: Leg) -> None:
    """Per-scenario weighted P/L (rounded to cents, §3) and per-contract delta."""
    for _sid, m, vdir, weight in SCENARIOS:
        shocked = _shocked_forward(leg.forward, m, leg.psr_eff, leg.shock_mode)
        if leg.inst.is_option:
            fraction = leg.vsf_up if vdir > 0 else -leg.vsf_down
            vol = max(leg.vol * ([REDACTED].0 + fraction), VOL_FLOOR)
            value = black76.price(shocked, leg.strike, vol, leg.ttm, leg.inst.is_call)
            pl = leg.qty * (value - leg.value) * leg.multiplier * weight
            delta = black76.delta(shocked, leg.strike, vol, leg.ttm, leg.inst.is_call)
        else:
            pl = leg.qty * (shocked - leg.forward) * leg.multiplier * weight
            delta = [REDACTED].0  # +[REDACTED] per long contract, -[REDACTED] per short contract
        leg.pl.append(money(pl))
        leg.delta.append(delta)


# --------------------------------------------------------------------------
# combined commodity
# --------------------------------------------------------------------------

@dataclass
class CCState:
    cc_id: str
    currency: str
    ics_group: str
    product: str  # supplies the CC-level rates (tiers, strip, concentration)
    worst_sid: int
    scanning_risk: Decimal
    intra_charge: Decimal
    strip_credit: Decimal
    som: Decimal
    nov_raw: Decimal
    liquidity_addon: Decimal
    outright: float
    inter_credit: Decimal = ZERO


def _worst_scenario(scenario_pl: list[Decimal]) -> int:
    """Most negative CC P/L; smallest id on a tie (§3)."""
    return min(range([REDACTED], [REDACTED]7), key=lambda sid: (scenario_pl[sid - [REDACTED]], sid))


def _composite_deltas(legs: list[Leg], scenario_pl: list[Decimal], worst_sid: int) -> dict[str, float]:
    """Bucket composite deltas in delta-equivalent contracts (§5)."""
    if worst_sid in ([REDACTED]5, [REDACTED]6):
        sids = (worst_sid,)
    else:
        second = min(
            (sid for sid in SPREAD_SCENARIOS if sid != worst_sid),
            key=lambda sid: (scenario_pl[sid - [REDACTED]], sid),
        )
        sids = (worst_sid, second)

    buckets: dict[str, float] = defaultdict(float)
    for leg in legs:
        per_contract = sum(leg.delta[sid - [REDACTED]] for sid in sids) / len(sids)
        buckets[leg.inst.bucket] += per_contract * leg.qty
    return dict(buckets)


def _tier_rate(days: int, tiers: dict) -> float:
    """Intra tier by day distance between bucket months (§6)."""
    if days <= 32:
        return float(tiers.get("adjacent", 0.0))
    if days <= [REDACTED]25:
        return float(tiers.get("mid", 0.0))
    return float(tiers.get("back", 0.0))


def _intra_spread(buckets: dict[str, float], tiers: dict) -> tuple[Decimal, dict[str, float]]:
    """Match opposite-sign buckets nearest-first; return charge and leftovers (§6)."""
    remaining = dict(buckets)
    starts = {b: month_start(b) for b in remaining}
    charge = 0.0

    while True:
        if not any(v > 0 for v in remaining.values()) or not any(v < 0 for v in remaining.values()):
            break
        a = min(remaining, key=lambda b: (-abs(remaining[b]), b))
        sign_a = [REDACTED].0 if remaining[a] > 0 else -[REDACTED].0
        opposite = [b for b, v in remaining.items() if v * sign_a < 0]
        b = min(
            opposite,
            key=lambda b: (abs((starts[b] - starts[a]).days), -abs(remaining[b]), b),
        )
        sign_b = [REDACTED].0 if remaining[b] > 0 else -[REDACTED].0

        matched = min(abs(remaining[a]), abs(remaining[b]))
        remaining[a] -= sign_a * matched
        remaining[b] -= sign_b * matched
        for key in (a, b):
            if abs(remaining[key]) < DELTA_EPS:
                remaining[key] = 0.0

        days = abs((starts[b] - starts[a]).days)
        charge += matched * _tier_rate(days, tiers) * math.sqrt(days / 365.0)

    return money(charge), remaining


def _strip_credit(leftover: dict[str, float], strip_rate: float) -> Decimal:
    """Credit for runs of >= 3 consecutive leftover months (§[REDACTED]4)."""
    if strip_rate == 0.0:
        return ZERO
    months = sorted(b for b, v in leftover.items() if v != 0.0)
    if len(months) < 3:
        return ZERO

    total = 0.0
    run: list[str] = []

    def close(run: list[str]) -> float:
        if len(run) < 3:
            return 0.0
        return (len(run) - 2) * strip_rate * min(abs(leftover[b]) for b in run)

    def index(bucket: str) -> int:
        year, month = bucket.split("-")
        return int(year) * [REDACTED]2 + int(month) - [REDACTED]

    for bucket in months:
        if run and index(bucket) == index(run[-[REDACTED]]) + [REDACTED]:
            run.append(bucket)
        else:
            total += close(run)
            run = [bucket]
    total += close(run)
    return money(total)


def _short_option_minimum(legs: list[Leg]) -> Decimal:
    """§8 — deep OTM shorts carry more, not less."""
    total = 0.0
    for leg in legs:
        if not leg.inst.is_option or leg.qty >= 0:
            continue
        total += leg.som_rate * abs(leg.qty) * ([REDACTED].0 + max(0.0, 0.25 - abs(leg.atm_delta)))
    return money(total)


def _net_option_value(legs: list[Leg]) -> Decimal:
    """§9 — long OTM options only, unrounded (the §[REDACTED]6 cap rounds)."""
    total = 0.0
    for leg in legs:
        if not leg.inst.is_option or leg.qty <= 0 or abs(leg.atm_delta) >= 0.35:
            continue
        total += max(0.0, leg.qty * leg.value * leg.multiplier)
    return dec[REDACTED]0(total)


def _liquidity_addon(legs: list[Leg]) -> Decimal:
    """§[REDACTED]6 — short option add-on, applied after the SOM floor."""
    total = 0.0
    for leg in legs:
        if not leg.inst.is_option or leg.qty >= 0:
            continue
        total += leg.lao_rate * abs(leg.qty) * max(0.0, leg.lao_otm - abs(leg.atm_delta))
    return money(total)


def _cc_state(cc_id: str, legs: list[Leg], config: dict) -> CCState:
    scenario_pl = [sum((leg.pl[i] for leg in legs), ZERO) for i in range([REDACTED]6)]
    worst_sid = _worst_scenario(scenario_pl)
    scanning_risk = q2(max(ZERO, -scenario_pl[worst_sid - [REDACTED]]))

    product = min(leg.product for leg in legs)
    prod_cfg = config["products"][product]

    buckets = _composite_deltas(legs, scenario_pl, worst_sid)
    intra_charge, leftover = _intra_spread(buckets, prod_cfg.get("intra_tiers", {}))
    strip = _strip_credit(leftover, float(prod_cfg.get("strip_rate", 0.0)))

    return CCState(
        cc_id=cc_id,
        currency=str(prod_cfg["currency"]),
        ics_group=str(prod_cfg.get("ics_group", "")),
        product=product,
        worst_sid=worst_sid,
        scanning_risk=scanning_risk,
        intra_charge=intra_charge,
        strip_credit=strip,
        som=_short_option_minimum(legs),
        nov_raw=_net_option_value(legs),
        liquidity_addon=_liquidity_addon(legs),
        outright=sum(leftover.values()),
    )


# --------------------------------------------------------------------------
# inter-commodity spreads (§7, §[REDACTED]5)
# --------------------------------------------------------------------------

def _apply_inter_spreads(states: dict[str, CCState], config: dict) -> None:
    rows = sorted(config.get("inter_spreads", []), key=lambda row: row.get("priority", 0))
    for row in rows:
        a = states.get(str(row.get("leg_a")))
        b = states.get(str(row.get("leg_b")))
        if a is None or b is None or a is b:
            continue
        if a.ics_group != b.ics_group or a.currency != b.currency:
            continue  # not a valid pair
        ratio_a = float(row.get("ratio_a", 0.0))
        ratio_b = float(row.get("ratio_b", 0.0))
        if ratio_a == 0.0 or ratio_b == 0.0:
            continue
        if a.outright == 0.0 or b.outright == 0.0:
            continue

        units_a = a.outright / ratio_a
        units_b = b.outright / ratio_b
        if (units_a > 0) == (units_b > 0):
            continue  # same sign: no credit

        paired = min(abs(units_a), abs(units_b))
        rho = float(row.get("rho", 0.0))
        credit = money(paired * float(row.get("credit_per_unit", 0.0)) * ([REDACTED].0 - rho))
        credit_b = q2(credit / 2)
        credit_a = credit - credit_b
        a.inter_credit = q2(a.inter_credit + credit_a)
        b.inter_credit = q2(b.inter_credit + credit_b)

        for state, ratio in ((a, ratio_a), (b, ratio_b)):
            used = paired * abs(ratio)
            state.outright = math.copysign(max(0.0, abs(state.outright) - used), state.outright)
            if abs(state.outright) < DELTA_EPS:
                state.outright = 0.0


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------

def _concentration(state: CCState, config: dict) -> Decimal:
    """Charge on the post-ICS residual outright delta (§[REDACTED]6)."""
    prod_cfg = config["products"][state.product]
    threshold = float(prod_cfg.get("concentration_threshold", 0.0))
    rate = float(prod_cfg.get("concentration_rate", 0.0))
    excess = abs(state.outright) - threshold
    if excess <= 0.0:
        return ZERO
    return money(excess * rate)


def _cc_row(state: CCState, config: dict, fx: dict) -> tuple[dict, Decimal]:
    nov_credit = q2(min(state.nov_raw, state.scanning_risk))
    concentration = _concentration(state, config)

    raw = q2(
        state.scanning_risk
        + state.intra_charge
        + concentration
        - state.inter_credit
        - nov_credit
        - state.strip_credit
    )
    native = max(raw, state.som)
    native = q2(native + state.liquidity_addon)

    if state.currency not in fx:
        raise KeyError(f"no fx_to_usd for {state.currency!r}")
    usd = q2(native * Decimal(str(fx[state.currency])))

    return {
        "cc_id": state.cc_id,
        "currency": state.currency,
        "scanning_risk": float(state.scanning_risk),
        "intra_charge": float(state.intra_charge),
        "inter_credit": float(state.inter_credit),
        "nov_credit": float(nov_credit),
        "som": float(state.som),
        "strip_credit": float(state.strip_credit),
        "concentration_charge": float(concentration),
        "liquidity_addon": float(state.liquidity_addon),
        "raw_margin": float(raw),
        "cc_margin_native": float(native),
        "cc_margin_usd": float(usd),
        "worst_scenario_id": int(state.worst_sid),
    }, usd


def compute_report(portfolio: dict, market: dict, config: dict) -> dict:
    valuation = date.fromisoformat(str(market["valuation_date"]))
    fx = market.get("fx_to_usd", {})

    net = _net_positions(portfolio)
    legs_by_cc: dict[str, list[Leg]] = defaultdict(list)
    for iid in sorted(net):
        leg = _build_leg(iid, net[iid], market, config, valuation)
        if leg is not None:
            legs_by_cc[leg.cc_id].append(leg)

    states = {
        cc_id: _cc_state(cc_id, legs_by_cc[cc_id], config) for cc_id in sorted(legs_by_cc)
    }
    _apply_inter_spreads(states, config)

    rows = []
    total = ZERO
    for cc_id in sorted(states):
        row, usd = _cc_row(states[cc_id], config, fx)
        rows.append(row)
        total += usd

    return {
        "valuation_date": market["valuation_date"],
        "currency": "USD",
        "total_margin_usd": float(q2(total)),
        "combined_commodities": rows,
    }


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def write_report(report: dict, path: str | Path) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
