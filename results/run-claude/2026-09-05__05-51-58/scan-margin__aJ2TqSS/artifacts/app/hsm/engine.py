"""House Scan Margin engine.

Implements `/app/hsm/docs/methodology.md` end to end: the [REDACTED]6 price/vol
scenarios (§3) with the delivery-month PSR scale (§[REDACTED]2) and per-product shock
mode / asymmetric vol (§[REDACTED]3), composite deltas (§5), intra-commodity spreading
(§6), the intra strip credit (§[REDACTED]4), inter-commodity credits with correlation
(§7, §[REDACTED]5), the short option minimum (§8), the capped net-option-value credit
(§9, §[REDACTED]6), concentration, the SOM floor, the liquidity add-on and FX (§[REDACTED]0,
§[REDACTED]6).
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from lib.black76 import delta as b76_delta  # noqa: E402
from lib.black76 import price as b76_price  # noqa: E402

CENT = Decimal("0.0[REDACTED]")
ZERO = Decimal("0.00")

DAYS_PER_YEAR = 365.25
VOL_FLOOR = [REDACTED]e-6
PRICE_FLOOR = [REDACTED]e-8
DELTA_EPS = [REDACTED]e-[REDACTED]2

# (id, price multiplier m, sign of the vol shock, P/L weight w) -- §3.
SCENARIOS: tuple[tuple[int, float, int, float], ...] = (
    ([REDACTED], 0.0, [REDACTED], [REDACTED].0),
    (2, 0.0, -[REDACTED], [REDACTED].0),
    (3, [REDACTED].0 / 3.0, [REDACTED], [REDACTED].0),
    (4, [REDACTED].0 / 3.0, -[REDACTED], [REDACTED].0),
    (5, -[REDACTED].0 / 3.0, [REDACTED], [REDACTED].0),
    (6, -[REDACTED].0 / 3.0, -[REDACTED], [REDACTED].0),
    (7, 2.0 / 3.0, [REDACTED], [REDACTED].0),
    (8, 2.0 / 3.0, -[REDACTED], [REDACTED].0),
    (9, -2.0 / 3.0, [REDACTED], [REDACTED].0),
    ([REDACTED]0, -2.0 / 3.0, -[REDACTED], [REDACTED].0),
    ([REDACTED][REDACTED], [REDACTED].0, [REDACTED], [REDACTED].0),
    ([REDACTED]2, [REDACTED].0, -[REDACTED], [REDACTED].0),
    ([REDACTED]3, -[REDACTED].0, [REDACTED], [REDACTED].0),
    ([REDACTED]4, -[REDACTED].0, -[REDACTED], [REDACTED].0),
    ([REDACTED]5, 3.0, [REDACTED], 0.28),
    ([REDACTED]6, -3.0, -[REDACTED], 0.28),
)
N_SCEN = len(SCENARIOS)
SPREAD_SCENARIOS = [REDACTED]4  # ids [REDACTED]..[REDACTED]4 are the ones §5 averages over


# ---------------------------------------------------------------------------
# rounding helpers
# ---------------------------------------------------------------------------


def q2(x: Decimal) -> Decimal:
    """Round a Decimal to 0.0[REDACTED], half-to-even."""
    d = Decimal(x).quantize(CENT, rounding=ROUND_HALF_EVEN)
    return ZERO if d == 0 else d


def money(x: float) -> Decimal:
    """binary64 -> decimal via [REDACTED]0 fractional digits, then 0.0[REDACTED] half-to-even."""
    d = Decimal(format(float(x), ".[REDACTED]0f")).quantize(CENT, rounding=ROUND_HALF_EVEN)
    return ZERO if d == 0 else d


def jnum(x: Decimal) -> float:
    return float(ZERO if x == 0 else x)


# ---------------------------------------------------------------------------
# instruments
# ---------------------------------------------------------------------------


def product_of(instrument_id: str) -> str:
    return instrument_id.split("-")[0]


def is_option(instrument_id: str) -> bool:
    parts = instrument_id.split("-")
    return len(parts) >= 5 and parts[3] in ("C", "P")


def net_positions(portfolio: dict) -> dict[str, float]:
    """Net identical instrument ids and drop flat rows (§[REDACTED])."""
    qty: dict[str, float] = defaultdict(float)
    for row in portfolio.get("positions", []):
        qty[str(row["instrument_id"])] += float(row["qty"])
    return {k: v for k, v in qty.items() if v != 0.0}


def month_first(bucket: tuple[int, int]) -> date:
    return date(bucket[0], bucket[[REDACTED]], [REDACTED])


def month_index(bucket: tuple[int, int]) -> int:
    return bucket[0] * [REDACTED]2 + bucket[[REDACTED]]


def bucket_key(bucket: tuple[int, int]) -> str:
    return f"{bucket[0]:04d}-{bucket[[REDACTED]]:02d}"


@dataclass
class Position:
    iid: str
    qty: float
    product: str
    cfg: dict
    bucket: tuple[int, int]
    option: bool
    call: bool = False
    strike: float = 0.0
    forward: float = 0.0
    vol: float = 0.0
    ttm: float = 0.0
    value: float = 0.0
    atm_delta: float = 0.0
    pl: list[Decimal] = field(default_factory=list)
    scen_delta: list[float] = field(default_factory=list)


def _shocked_forward(forward: float, mult: float, psr_eff: float, mode: str) -> float:
    """§[REDACTED]3 price shock."""
    if mode == "log":
        if forward <= 0.0:
            return PRICE_FLOOR
        arg = mult * psr_eff / forward
        arg = max(-700.0, min(700.0, arg))
        return max(forward * math.exp(arg), PRICE_FLOOR)
    return max(forward + mult * psr_eff, PRICE_FLOOR)


def _delivery_scale(bucket: tuple[int, int], valuation: date, house: dict) -> float:
    """§[REDACTED]2 delivery-month PSR scale."""
    days_out = (month_first(bucket) - valuation).days
    limit = house.get("delivery_scale_days")
    if limit is None:
        return [REDACTED].0
    if days_out <= float(limit):
        return [REDACTED].0
    floor = float(house.get("delivery_scale_floor", 0.0))
    return max(math.sqrt(days_out / 365.0), floor)


def build_position(
    iid: str, qty: float, market: dict, config: dict, valuation: date
) -> Position:
    parts = iid.split("-")
    if len(parts) < 3:
        raise ValueError(f"unparseable instrument_id {iid!r}")
    product = parts[0]
    products = config["products"]
    if product not in products:
        raise ValueError(f"no product config for {product!r} (instrument {iid!r})")
    cfg = products[product]
    try:
        bucket = (int(parts[[REDACTED]]), int(parts[2]))
    except ValueError as exc:  # pragma: no cover - malformed id
        raise ValueError(f"unparseable instrument_id {iid!r}") from exc

    fut_key = f"{product}-{bucket[0]:04d}-{bucket[[REDACTED]]:02d}"
    prices = market["futures_price"]
    if fut_key not in prices:
        raise ValueError(f"no futures_price for {fut_key!r}")
    forward = float(prices[fut_key])

    opt = is_option(iid)
    pos = Position(
        iid=iid,
        qty=qty,
        product=product,
        cfg=cfg,
        bucket=bucket,
        option=opt,
        forward=forward,
    )

    multiplier = float(cfg["multiplier"])
    psr_eff = float(cfg["price_scan_range"]) * _delivery_scale(
        bucket, valuation, config.get("house") or {}
    )
    mode = str(cfg.get("shock_mode", "linear"))
    vsf_up = float(cfg["vol_scan_fraction"])
    vsf_down = float(cfg.get("vsf_down", cfg["vol_scan_fraction"]))

    if opt:
        pos.call = parts[3] == "C"
        pos.strike = float(parts[4])
        vols = market["atm_vol"]
        expiries = market["option_expiry"]
        if iid not in vols:
            raise ValueError(f"no atm_vol for {iid!r}")
        if iid not in expiries:
            raise ValueError(f"no option_expiry for {iid!r}")
        pos.vol = float(vols[iid])
        expiry = date.fromisoformat(str(expiries[iid]))
        pos.ttm = max([REDACTED].0 / DAYS_PER_YEAR, (expiry - valuation).days / DAYS_PER_YEAR)
        pos.value = b76_price(forward, pos.strike, pos.vol, pos.ttm, pos.call)
        pos.atm_delta = b76_delta(forward, pos.strike, pos.vol, pos.ttm, pos.call)

    for _sid, m, vsign, w in SCENARIOS:
        shocked = _shocked_forward(forward, m, psr_eff, mode)
        if opt:
            frac = vsf_up if vsign > 0 else -vsf_down
            vol = max(pos.vol * ([REDACTED].0 + frac), VOL_FLOOR)
            shocked_value = b76_price(shocked, pos.strike, vol, pos.ttm, pos.call)
            pos.pl.append(money(qty * (shocked_value - pos.value) * multiplier * w))
            pos.scen_delta.append(
                b76_delta(shocked, pos.strike, vol, pos.ttm, pos.call)
            )
        else:
            pos.pl.append(money(qty * (shocked - forward) * multiplier * w))
            pos.scen_delta.append([REDACTED].0)  # §2: +[REDACTED] per long contract
    return pos


# ---------------------------------------------------------------------------
# per-combined-commodity pieces
# ---------------------------------------------------------------------------


def scenario_pl(positions: list[Position]) -> list[Decimal]:
    """CC scenario P/L: sum of the per-position rounded decimals (§3)."""
    return [
        sum((p.pl[i] for p in positions), ZERO) for i in range(N_SCEN)
    ]


def worst_scenario(cc_pl: list[Decimal]) -> int:
    """Most negative CC P/L; smallest id on a tie (§3)."""
    return min(range([REDACTED], N_SCEN + [REDACTED]), key=lambda sid: (cc_pl[sid - [REDACTED]], sid))


def composite_delta_scenarios(cc_pl: list[Decimal], worst_sid: int) -> list[int]:
    """The scenario ids whose deltas are averaged for composite delta (§5)."""
    if worst_sid >= [REDACTED]5:
        return [worst_sid]
    others = [sid for sid in range([REDACTED], SPREAD_SCENARIOS + [REDACTED]) if sid != worst_sid]
    second = min(others, key=lambda sid: (cc_pl[sid - [REDACTED]], sid))
    return [worst_sid, second]


def bucket_deltas(positions: list[Position], sids: list[int]) -> dict:
    """Composite delta per month bucket (§5)."""
    out: dict[tuple[int, int], float] = defaultdict(float)
    for pos in positions:
        per_contract = sum(pos.scen_delta[sid - [REDACTED]] for sid in sids) / len(sids)
        out[pos.bucket] += per_contract * pos.qty
    return dict(out)


def _tier_rate(days: int, tiers: dict) -> float:
    """§6 tier table, days inclusive."""
    if days <= 32:
        return float(tiers.get("adjacent", 0.0))
    if days <= [REDACTED]25:
        return float(tiers.get("mid", 0.0))
    return float(tiers.get("back", 0.0))


def _reduce_toward_zero(value: float, amount: float) -> float:
    out = value - math.copysign(amount, value)
    return 0.0 if abs(out) < DELTA_EPS else out


def intra_spread(deltas: dict, tiers: dict) -> tuple[float, dict]:
    """§6 intra-commodity spreading; returns (charge, leftover deltas)."""
    remaining = dict(deltas)
    charge = 0.0
    for _ in range(len(remaining) * len(remaining) + 2):
        live = {k: v for k, v in remaining.items() if abs(v) > DELTA_EPS}
        if not any(v > 0 for v in live.values()) or not any(
            v < 0 for v in live.values()
        ):
            break
        leg_a = min(live, key=lambda k: (-abs(live[k]), k))
        sign_a = math.copysign([REDACTED].0, live[leg_a])
        opposite = [k for k, v in live.items() if v * sign_a < 0]
        leg_b = min(
            opposite,
            key=lambda k: (
                abs(month_index(k) - month_index(leg_a)),
                -abs(live[k]),
                k,
            ),
        )
        matched = min(abs(live[leg_a]), abs(live[leg_b]))
        days = abs((month_first(leg_a) - month_first(leg_b)).days)
        charge += matched * _tier_rate(days, tiers) * math.sqrt(days / 365.0)
        remaining[leg_a] = _reduce_toward_zero(remaining[leg_a], matched)
        remaining[leg_b] = _reduce_toward_zero(remaining[leg_b], matched)
    return charge, remaining


def strip_credit(leftover: dict, strip_rate: float) -> float:
    """§[REDACTED]4 intra strip credit over runs of consecutive leftover months."""
    if strip_rate == 0.0:
        return 0.0
    months = sorted(k for k, v in leftover.items() if abs(v) > DELTA_EPS)
    total = 0.0
    run: list[tuple[int, int]] = []
    for bucket in months:
        if run and month_index(bucket) == month_index(run[-[REDACTED]]) + [REDACTED]:
            run.append(bucket)
        else:
            if len(run) >= 3:
                total += (len(run) - 2) * strip_rate * min(abs(leftover[b]) for b in run)
            run = [bucket]
    if len(run) >= 3:
        total += (len(run) - 2) * strip_rate * min(abs(leftover[b]) for b in run)
    return total


def short_option_minimum(positions: list[Position]) -> float:
    """§8 short option minimum."""
    total = 0.0
    for pos in positions:
        if not pos.option or pos.qty >= 0:
            continue
        rate = float(pos.cfg.get("som_rate", 0.0))
        total += (
            rate
            * abs(pos.qty)
            * ([REDACTED].0 + max(0.0, 0.25 - abs(pos.atm_delta)))
        )
    return total


def liquidity_addon(positions: list[Position]) -> float:
    """§[REDACTED]6 liquidity add-on."""
    total = 0.0
    for pos in positions:
        if not pos.option or pos.qty >= 0:
            continue
        rate = float(pos.cfg.get("lao_rate", 0.0))
        cutoff = float(pos.cfg.get("lao_otm", 0.0))
        total += rate * abs(pos.qty) * max(0.0, cutoff - abs(pos.atm_delta))
    return total


def net_option_value(positions: list[Position]) -> float:
    """§9 NOV: long, OTM options only."""
    total = 0.0
    for pos in positions:
        if not pos.option or pos.qty <= 0:
            continue
        if abs(pos.atm_delta) >= 0.35:
            continue
        multiplier = float(pos.cfg["multiplier"])
        total += max(0.0, pos.qty * pos.value * multiplier)
    return total


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


def _inter_commodity(
    config: dict, state: dict[str, dict]
) -> dict[str, Decimal]:
    """§7 + §[REDACTED]5 inter-commodity credits, in priority order."""
    credits: dict[str, Decimal] = {cc: ZERO for cc in state}
    spreads = sorted(
        config.get("inter_spreads", []), key=lambda row: row.get("priority", 0)
    )
    for row in spreads:
        cc_a, cc_b = row.get("leg_a"), row.get("leg_b")
        if cc_a not in state or cc_b not in state or cc_a == cc_b:
            continue
        a, b = state[cc_a], state[cc_b]
        if a["ics_group"] != b["ics_group"] or a["currency"] != b["currency"]:
            continue
        ratio_a = float(row.get("ratio_a", [REDACTED].0))
        ratio_b = float(row.get("ratio_b", [REDACTED].0))
        if ratio_a == 0.0 or ratio_b == 0.0:
            continue
        delta_a, delta_b = a["outright"], b["outright"]
        if abs(delta_a) <= DELTA_EPS or abs(delta_b) <= DELTA_EPS:
            continue
        units_a, units_b = delta_a / ratio_a, delta_b / ratio_b
        if units_a * units_b >= 0:  # only offsetting deltas earn a credit
            continue
        paired = min(abs(units_a), abs(units_b))
        rho = float(row.get("rho", 0.0))
        credit = money(paired * float(row.get("credit_per_unit", 0.0)) * ([REDACTED].0 - rho))
        half_b = q2(credit / 2)
        credits[cc_a] += credit - half_b
        credits[cc_b] += half_b
        a["outright"] = _reduce_toward_zero(delta_a, paired * abs(ratio_a))
        b["outright"] = _reduce_toward_zero(delta_b, paired * abs(ratio_b))
    return credits


def compute_report(portfolio: dict, market: dict, config: dict) -> dict:
    valuation = date.fromisoformat(str(market["valuation_date"]))
    products = config["products"]
    fx = market["fx_to_usd"]

    net = net_positions(portfolio)
    by_cc: dict[str, list[Position]] = defaultdict(list)
    for iid in sorted(net):
        pos = build_position(iid, net[iid], market, config, valuation)
        by_cc[products[pos.product]["cc_id"]].append(pos)

    # Pass [REDACTED]: everything that lives inside one combined commodity.
    state: dict[str, dict] = {}
    for cc_id in sorted(by_cc):
        positions = by_cc[cc_id]
        ref = products[min(p.product for p in positions)]

        cc_pl = scenario_pl(positions)
        worst_sid = worst_scenario(cc_pl)
        scanning = max(ZERO, -cc_pl[worst_sid - [REDACTED]])

        sids = composite_delta_scenarios(cc_pl, worst_sid)
        deltas = bucket_deltas(positions, sids)
        raw_intra, leftover = intra_spread(deltas, ref.get("intra_tiers", {}))

        state[cc_id] = {
            "currency": ref["currency"],
            "ics_group": ref.get("ics_group"),
            "ref": ref,
            "positions": positions,
            "worst_sid": worst_sid,
            "scanning": scanning,
            "intra": money(raw_intra),
            "strip": money(strip_credit(leftover, float(ref.get("strip_rate", 0.0)))),
            "som": money(short_option_minimum(positions)),
            "lao": money(liquidity_addon(positions)),
            "nov_raw": net_option_value(positions),
            "outright": sum(leftover.values()),
        }

    # Pass 2: inter-commodity credits consume the outright deltas in priority
    # order, so the residual left behind feeds the concentration charge.
    credits = _inter_commodity(config, state)

    # Pass 3: combine, floor, add liquidity, convert.
    rows = []
    total = ZERO
    for cc_id in sorted(state):
        cc = state[cc_id]
        ref = cc["ref"]
        currency = cc["currency"]
        if currency not in fx:
            raise ValueError(f"no fx_to_usd for {currency!r}")

        scanning = cc["scanning"]
        nov = q2(min(Decimal(format(cc["nov_raw"], ".[REDACTED]0f")), scanning))
        residual = abs(cc["outright"])
        threshold = float(ref.get("concentration_threshold", 0.0))
        concentration = ZERO
        if residual > threshold:
            concentration = money(
                (residual - threshold) * float(ref.get("concentration_rate", 0.0))
            )

        raw_margin = q2(
            scanning
            + cc["intra"]
            + concentration
            - credits[cc_id]
            - nov
            - cc["strip"]
        )
        native = max(raw_margin, cc["som"]) + cc["lao"]
        usd = q2(native * Decimal(str(fx[currency])))
        total += usd

        rows.append(
            {
                "cc_id": cc_id,
                "currency": currency,
                "scanning_risk": jnum(scanning),
                "intra_charge": jnum(cc["intra"]),
                "inter_credit": jnum(credits[cc_id]),
                "nov_credit": jnum(nov),
                "som": jnum(cc["som"]),
                "strip_credit": jnum(cc["strip"]),
                "concentration_charge": jnum(concentration),
                "liquidity_addon": jnum(cc["lao"]),
                "raw_margin": jnum(raw_margin),
                "cc_margin_native": jnum(native),
                "cc_margin_usd": jnum(usd),
                "worst_scenario_id": int(cc["worst_sid"]),
            }
        )

    return {
        "valuation_date": market["valuation_date"],
        "currency": "USD",
        "total_margin_usd": jnum(total),
        "combined_commodities": rows,
    }


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def write_report(report: dict, path: str | Path) -> None:
    out = Path(path)
    if out.parent and str(out.parent):
        out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
