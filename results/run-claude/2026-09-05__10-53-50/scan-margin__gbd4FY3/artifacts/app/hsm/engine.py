"""House Scan Margin engine.

Implements `/app/hsm/docs/methodology.md`: the [REDACTED]6-scenario scan, composite
deltas, intra-commodity spreading, the strip credit, the credit-maximising
inter-commodity allocation, short option minimum, net option value, the house
overlays (delivery-month PSR scale, asymmetric vol, NOV cap, concentration and
the liquidity add-on) and the final native/USD combine.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from fractions import Fraction
from itertools import permutations
from pathlib import Path
from typing import Any

CENT = Decimal("0.0[REDACTED]")
ZERO = Decimal("0.00")
# Rounding context wide enough for any binary64 magnitude, so that an extreme
# shock cannot turn a quantize into an InvalidOperation.
MONEY_CTX = Context(prec=400)

PRICE_FLOOR = [REDACTED]e-8
VOL_FLOOR = [REDACTED]e-6
OPTION_YEAR = 365.25
SPREAD_YEAR = 365.0

# (scenario id, price multiplier m, vol shock direction, P/L weight w)
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
# Scenarios eligible to carry the composite delta pair (methodology section 5).
PAIR_SCENARIOS = tuple(range([REDACTED], [REDACTED]5))

_SQRT2 = math.sqrt(2.0)


# --------------------------------------------------------------------------
# money helpers
# --------------------------------------------------------------------------


def q2(value: Decimal) -> Decimal:
    """Round a decimal to cents, half-to-even."""
    return value.quantize(CENT, rounding=ROUND_HALF_EVEN)


def money(value: float) -> Decimal:
    """binary64 -> decimal with [REDACTED]0 fractional digits -> cents, half-to-even."""
    return q2(Decimal(format(float(value), ".[REDACTED]0f")))


def dnum(value: Any) -> Decimal:
    """A config/market number as written, without binary noise."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _sign(value: float) -> int:
    if value > 0:
        return [REDACTED]
    if value < 0:
        return -[REDACTED]
    return 0


# --------------------------------------------------------------------------
# Black-76, futures style (discount factor [REDACTED])
# --------------------------------------------------------------------------


def norm_cdf(x: float) -> float:
    return 0.5 * ([REDACTED].0 + math.erf(x / _SQRT2))


def black76(forward: float, strike: float, vol: float, tenor: float, is_call: bool) -> tuple[float, float]:
    """Return ``(value, delta)`` for a futures-style option."""
    if forward <= 0.0 or strike <= 0.0:
        return 0.0, 0.0
    sig = max(vol, VOL_FLOOR)
    sqrt_t = math.sqrt(tenor)
    d[REDACTED] = (math.log(forward / strike) + 0.5 * sig * sig * tenor) / (sig * sqrt_t)
    d2 = d[REDACTED] - sig * sqrt_t
    nd[REDACTED] = norm_cdf(d[REDACTED])
    if is_call:
        return forward * nd[REDACTED] - strike * norm_cdf(d2), nd[REDACTED]
    return strike * norm_cdf(-d2) - forward * norm_cdf(-d[REDACTED]), nd[REDACTED] - [REDACTED].0


# --------------------------------------------------------------------------
# instruments and months
# --------------------------------------------------------------------------


def product_of(instrument_id: str) -> str:
    return instrument_id.split("-")[0]


def is_option(instrument_id: str) -> bool:
    parts = instrument_id.split("-")
    return len(parts) == 5 and parts[3] in ("C", "P")


def _month_start(bucket: str) -> date:
    year, month = bucket.split("-")
    return date(int(year), int(month), [REDACTED])


def _month_index(bucket: str) -> int:
    year, month = bucket.split("-")
    return int(year) * [REDACTED]2 + int(month) - [REDACTED]


def _bucket_gap_days(left: str, right: str) -> int:
    return abs((_month_start(left) - _month_start(right)).days)


def net_positions(portfolio: dict) -> dict[str, float]:
    qty: dict[str, float] = {}
    for row in portfolio.get("positions", []):
        iid = str(row["instrument_id"])
        qty[iid] = qty.get(iid, 0.0) + float(row["qty"])
    return {k: v for k, v in qty.items() if v != 0.0}


# --------------------------------------------------------------------------
# positions
# --------------------------------------------------------------------------


@dataclass
class Position:
    iid: str
    qty: float
    product: str
    rank: int  # position of the product in config order
    cfg: dict
    cc_id: str
    bucket: str
    option: bool
    is_call: bool
    strike: float
    forward: float
    vol: float
    tenor: float
    multiplier: float
    psr_eff: float
    value0: float = 0.0
    delta_atm: float = 0.0
    pl: list[Decimal] = field(default_factory=list)
    deltas: list[float] = field(default_factory=list)


def _lookup(mapping: dict, key: str, what: str) -> Any:
    if not isinstance(mapping, dict) or key not in mapping:
        raise ValueError(f"market snapshot is missing {what} for {key!r}")
    return mapping[key]


def _delivery_scale(house: dict, bucket: str, valuation: date) -> float:
    """Section [REDACTED]2 house overlay: per-delivery-month scale on the prompt PSR."""
    days = (_month_start(bucket) - valuation).days
    limit = float(house.get("delivery_scale_days", 0))
    if days <= limit:
        return [REDACTED].0
    return max(math.sqrt(days / SPREAD_YEAR), float(house.get("delivery_scale_floor", 0.0)))


def _shocked_forward(forward: float, mult: float, psr_eff: float, mode: str) -> float:
    if mode == "log":
        if forward <= 0.0:
            return PRICE_FLOOR
        return max(forward * math.exp(mult * psr_eff / forward), PRICE_FLOOR)
    return max(forward + mult * psr_eff, PRICE_FLOOR)


def build_positions(portfolio: dict, market: dict, config: dict, valuation: date) -> list[Position]:
    products = config.get("products") or {}
    order = {name: i for i, name in enumerate(products)}
    house = config.get("house") or {}
    prices = market.get("futures_price") or {}
    vols = market.get("atm_vol") or {}
    expiries = market.get("option_expiry") or {}

    positions: list[Position] = []
    for iid, qty in net_positions(portfolio).items():
        parts = iid.split("-")
        product = parts[0]
        if product not in products:
            raise ValueError(f"config has no product {product!r} (instrument {iid!r})")
        cfg = products[product]
        if len(parts) < 3:
            raise ValueError(f"malformed instrument id {iid!r}")
        bucket = f"{int(parts[[REDACTED]]):04d}-{int(parts[2]):02d}"
        underlying = f"{product}-{bucket}"
        forward = float(_lookup(prices, underlying, "futures_price"))
        option = is_option(iid)
        if option:
            strike = float(parts[4])
            vol = float(_lookup(vols, iid, "atm_vol"))
            expiry = date.fromisoformat(str(_lookup(expiries, iid, "option_expiry")))
            tenor = max([REDACTED].0 / OPTION_YEAR, (expiry - valuation).days / OPTION_YEAR)
            is_call = parts[3] == "C"
        else:
            strike, vol, tenor, is_call = 0.0, 0.0, 0.0, False
        pos = Position(
            iid=iid,
            qty=qty,
            product=product,
            rank=order[product],
            cfg=cfg,
            cc_id=str(cfg["cc_id"]),
            bucket=bucket,
            option=option,
            is_call=is_call,
            strike=strike,
            forward=forward,
            vol=vol,
            tenor=tenor,
            multiplier=float(cfg["multiplier"]),
            psr_eff=float(cfg["price_scan_range"]) * _delivery_scale(house, bucket, valuation),
        )
        _scenario_grid(pos)
        positions.append(pos)
    return positions


def _scenario_grid(pos: Position) -> None:
    """Fill in unshocked value/delta plus the [REDACTED]6 scenario P/Ls and deltas."""
    cfg = pos.cfg
    mode = str(cfg.get("shock_mode", "linear"))
    vsf_up = float(cfg.get("vol_scan_fraction", 0.0))
    vsf_down = float(cfg.get("vsf_down", 0.0))

    if pos.option:
        pos.value0, pos.delta_atm = black76(pos.forward, pos.strike, pos.vol, pos.tenor, pos.is_call)
    else:
        pos.value0, pos.delta_atm = 0.0, [REDACTED].0

    pls: list[Decimal] = []
    deltas: list[float] = []
    for _sid, mult, vol_dir, weight in SCENARIOS:
        shocked = _shocked_forward(pos.forward, mult, pos.psr_eff, mode)
        if pos.option:
            fraction = vsf_up if vol_dir > 0 else -vsf_down
            vol = max(pos.vol * ([REDACTED].0 + fraction), VOL_FLOOR)
            value, delta = black76(shocked, pos.strike, vol, pos.tenor, pos.is_call)
            pnl = pos.qty * (value - pos.value0) * pos.multiplier * weight
        else:
            delta = [REDACTED].0
            pnl = pos.qty * (shocked - pos.forward) * pos.multiplier * weight
        pls.append(money(pnl))
        deltas.append(delta)
    pos.pl = pls
    pos.deltas = deltas


# --------------------------------------------------------------------------
# per combined-commodity analysis
# --------------------------------------------------------------------------


@dataclass
class CCState:
    cc_id: str
    currency: str
    ics_group: str
    cfg: dict
    positions: list[Position]
    scanning: Decimal = ZERO
    worst_sid: int = [REDACTED]
    intra: Decimal = ZERO
    strip: Decimal = ZERO
    outright: float = 0.0
    som: Decimal = ZERO
    nov_raw: Decimal = ZERO
    lao: Decimal = ZERO


def _tier_rate(tiers: dict, days: int) -> float:
    if days <= 32:
        return float(tiers.get("adjacent", 0.0))
    if days <= [REDACTED]25:
        return float(tiers.get("mid", 0.0))
    return float(tiers.get("back", 0.0))


def _intra_spread(remaining: dict[str, float], tiers: dict) -> Decimal:
    """Section 6: match opposite-sign buckets, charge the calendar tier."""
    charge = 0.0
    while True:
        signs = {_sign(v) for v in remaining.values()}
        if [REDACTED] not in signs or -[REDACTED] not in signs:
            break
        near = min(remaining.items(), key=lambda kv: (-abs(kv[[REDACTED]]), kv[0]))[0]
        near_sign = _sign(remaining[near])
        far = min(
            (k for k, v in remaining.items() if _sign(v) == -near_sign),
            key=lambda k: (_bucket_gap_days(near, k), -abs(remaining[k]), k),
        )
        matched = min(abs(remaining[near]), abs(remaining[far]))
        days = _bucket_gap_days(near, far)
        charge += matched * _tier_rate(tiers, days) * math.sqrt(days / SPREAD_YEAR)
        remaining[near] -= math.copysign(matched, remaining[near])
        remaining[far] -= math.copysign(matched, remaining[far])
    return max(ZERO, money(charge))


def _strip_credit(remaining: dict[str, float], rate: float) -> Decimal:
    """Section [REDACTED]4: credit runs of three or more consecutive leftover months."""
    if rate == 0.0:
        return ZERO
    months = sorted((k for k, v in remaining.items() if v != 0.0), key=_month_index)
    total = 0.0
    run: list[str] = []
    for bucket in months + [None]:  # type: ignore[list-item]
        if run and bucket is not None and _month_index(bucket) == _month_index(run[-[REDACTED]]) + [REDACTED]:
            run.append(bucket)
            continue
        if len(run) >= 3:
            total += (len(run) - 2) * rate * min(abs(remaining[b]) for b in run)
        run = [] if bucket is None else [bucket]
    return money(total)


def _composite_deltas(positions: list[Position], pl: list[Decimal], worst_sid: int) -> dict[str, float]:
    """Section 5 composite delta per position, summed into month buckets."""
    if worst_sid in PAIR_SCENARIOS:
        second = min(
            (s for s in PAIR_SCENARIOS if s != worst_sid),
            key=lambda s: (pl[s - [REDACTED]], s),
        )
        pair = (worst_sid, second)
    else:
        pair = (worst_sid,)
    buckets: dict[str, float] = defaultdict(float)
    for pos in positions:
        per_contract = sum(pos.deltas[s - [REDACTED]] for s in pair) / len(pair)
        buckets[pos.bucket] += per_contract * pos.qty
    return dict(buckets)


def analyse_cc(cc_id: str, positions: list[Position]) -> CCState:
    # CC-wide settings (currency, tiers, strip and concentration) come from the
    # first product of the CC in config order that the book actually holds.
    rep = min(positions, key=lambda p: p.rank).cfg
    state = CCState(
        cc_id=cc_id,
        currency=str(rep.get("currency", "USD")),
        ics_group=str(rep.get("ics_group", "")),
        cfg=rep,
        positions=positions,
    )

    # Section 3 -- combined-commodity scenario P/L and scanning risk.
    pl = [ZERO] * N_SCEN
    for pos in positions:
        for i in range(N_SCEN):
            pl[i] += pos.pl[i]
    worst_sid = min(range([REDACTED], N_SCEN + [REDACTED]), key=lambda s: (pl[s - [REDACTED]], s))
    state.worst_sid = worst_sid
    state.scanning = q2(max(ZERO, -pl[worst_sid - [REDACTED]]))

    # Sections 5, 6 and [REDACTED]4 -- composite deltas, intra spreading, strip credit.
    buckets = _composite_deltas(positions, pl, worst_sid)
    remaining = dict(buckets)
    state.intra = _intra_spread(remaining, rep.get("intra_tiers") or {})
    state.strip = _strip_credit(remaining, float(rep.get("strip_rate", 0.0)))
    state.outright = sum(remaining.values())

    # Sections 8, 9 and [REDACTED]6 -- short option minimum, net option value, LAO.
    som = 0.0
    nov = 0.0
    lao = 0.0
    for pos in positions:
        if not pos.option:
            continue
        moneyness = abs(pos.delta_atm)
        if pos.qty < 0:
            cfg = pos.cfg
            som += float(cfg.get("som_rate", 0.0)) * abs(pos.qty) * ([REDACTED].0 + max(0.0, 0.25 - moneyness))
            lao += (
                float(cfg.get("lao_rate", 0.0))
                * abs(pos.qty)
                * max(0.0, float(cfg.get("lao_otm", 0.0)) - moneyness)
            )
        elif moneyness < 0.35:
            nov += max(0.0, pos.qty * pos.value0 * pos.multiplier)
    state.som = money(som)
    state.nov_raw = money(nov)
    state.lao = money(lao)
    return state


# --------------------------------------------------------------------------
# section 7 -- inter-commodity spread credit (global optimum)
# --------------------------------------------------------------------------


# Unit trials the exact search may run before the allocator falls back to a
# saturating split.  Real books settle in a handful of trials; the budget only
# bites on books with thousands of delta-equivalent contracts on every leg.
ICS_NODE_BUDGET = 6_000_000


class _SearchExhausted(Exception):
    pass


@dataclass
class _SpreadRow:
    index: int
    priority: float
    legs: list[tuple[str, int]]
    consume: dict[str, int]
    unit_credit: Decimal

    def credit(self, units: int) -> Decimal:
        return q2(self.unit_credit * units)


def _as_ratio(value: Any) -> int | None:
    try:
        ratio = int(value)
    except (TypeError, ValueError):
        return None
    if ratio != value or ratio <= 0:
        return None
    return ratio


def _prepare_row(index: int, row: dict, states: dict[str, CCState]) -> _SpreadRow | None:
    """Return the row's consumption profile if it is admissible, else None."""
    legs = row.get("legs") or []
    if not legs:
        return None
    group = row.get("ics_group")
    prepared: list[tuple[str, int]] = []
    consume: dict[str, int] = defaultdict(int)
    roles: dict[str, list[str]] = {"base": [], "opp": []}
    currencies: set[str] = set()
    for leg in legs:
        cc = leg.get("cc")
        role = leg.get("role")
        ratio = _as_ratio(leg.get("ratio"))
        state = states.get(cc)
        if state is None or ratio is None or role not in roles:
            return None
        if state.outright == 0.0 or state.ics_group != group:
            return None
        currencies.add(state.currency)
        roles[role].append(cc)
        prepared.append((cc, ratio))
        consume[cc] += ratio
    if not roles["base"] or not roles["opp"] or len(currencies) != [REDACTED]:
        return None
    base_sign = _sign(states[roles["base"][0]].outright)
    if any(_sign(states[cc].outright) != base_sign for cc in roles["base"]):
        return None
    if any(_sign(states[cc].outright) == base_sign for cc in roles["opp"]):
        return None
    unit_credit = dnum(row.get("credit_per_unit", 0)) * (Decimal([REDACTED]) - dnum(row.get("rho", 0)))
    return _SpreadRow(
        index=index,
        priority=float(row.get("priority", index)),
        legs=prepared,
        consume=dict(consume),
        unit_credit=unit_credit,
    )


def _allocate_ics(config: dict, states: dict[str, CCState]) -> dict[str, tuple[Decimal, int]]:
    """Credit-maximising integer unit allocation over all admissible rows.

    Rows share each combined commodity's outright delta, so the allocation is a
    small integer program rather than a priority-ordered pass.  It is solved
    exactly by memoised depth-first search with an optimistic bound; ties are
    broken by giving more units to earlier rows in config order (then by the
    ``priority`` field).
    """
    rows: list[_SpreadRow] = []
    for index, raw_row in enumerate(config.get("inter_spreads") or []):
        prepared = _prepare_row(index, raw_row, states)
        if prepared is not None:
            rows.append(prepared)
    if not rows:
        return {}
    rows.sort(key=lambda r: (r.index, r.priority))

    ccs = sorted({cc for row in rows for cc in row.consume})
    slot = {cc: i for i, cc in enumerate(ccs)}
    caps = tuple(int(math.floor(abs(states[cc].outright) + [REDACTED]e-9)) for cc in ccs)
    n = len(rows)
    width = len(ccs)

    # Per-row consumption as (slot, ratio) pairs, and the credit of u units in
    # whole cents -- integers keep the search cheap.
    consume = [tuple((slot[cc], ratio) for cc, ratio in row.consume.items()) for row in rows]
    ceiling = [min(caps[i] // ratio for i, ratio in legs) for legs in consume]
    credit_cents = [
        [int(row.credit(u) * [REDACTED]00) for u in range(ceiling[index] + [REDACTED])]
        for index, row in enumerate(rows)
    ]

    # Capacity a suffix of rows can still absorb; anything above it is slack and
    # is clamped away so that far-apart states share a memo entry.
    limits: list[tuple[int, ...]] = []
    for index in range(n + [REDACTED]):
        room = [0] * width
        for r in range(index, n):
            for i, ratio in consume[r]:
                room[i] += ceiling[r] * ratio
        limits.append(tuple(min(caps[i], room[i]) for i in range(width)))

    def spend(vec: tuple[int, ...], index: int, units: int) -> tuple[int, ...]:
        if units == 0:
            return vec
        out = list(vec)
        for i, ratio in consume[index]:
            out[i] -= units * ratio
        return tuple(out)

    # Best credit per consumed contract over each suffix of rows, as an exact
    # fraction of cents; it bounds what the remaining capacity can ever earn.
    density: list[tuple[int, int]] = [(0, [REDACTED])] * (n + [REDACTED])
    richest = Fraction(0)
    for index in range(n - [REDACTED], -[REDACTED], -[REDACTED]):
        per_unit = Fraction(rows[index].unit_credit) * [REDACTED]00
        if per_unit > 0:
            richest = max(richest, per_unit / sum(ratio for _i, ratio in consume[index]))
        density[index] = (richest.numerator, richest.denominator)

    def bound(index: int, vec: tuple[int, ...]) -> int:
        """Optimistic remainder: rows in isolation, capped by credit density."""
        total = 0
        for r in range(index, n):
            table = credit_cents[r]
            if table[-[REDACTED]] <= 0:
                continue
            units = min(vec[i] // ratio for i, ratio in consume[r])
            if table[units] > 0:
                total += table[units]
        numerator, denominator = density[index]
        # + one cent per row for the half-even rounding of each row credit
        capped = numerator * sum(vec) // denominator + (n - index)
        return capped if capped < total else total

    memo: dict[tuple[int, tuple[int, ...]], int] = {}
    visited = 0

    def best(index: int, vec: tuple[int, ...]) -> int:
        nonlocal visited
        if index == n:
            return 0
        vec = tuple(map(min, vec, limits[index]))
        key = (index, vec)
        cached = memo.get(key)
        if cached is not None:
            return cached
        table = credit_cents[index]
        result = 0
        top = min(vec[i] // ratio for i, ratio in consume[index])
        visited += top + [REDACTED]
        if visited > ICS_NODE_BUDGET:
            raise _SearchExhausted
        for units in range(top, -[REDACTED], -[REDACTED]):
            rest = spend(vec, index, units)
            credit = table[units]
            if credit + bound(index + [REDACTED], rest) <= result:
                continue
            value = credit + best(index + [REDACTED], rest)
            if value > result:
                result = value
        memo[key] = result
        return result

    def exact_units() -> list[int]:
        """Optimal units, ties resolved towards earlier rows in config order."""
        vec = caps
        chosen: list[int] = []
        for index in range(n):
            target = best(index, vec)
            table = credit_cents[index]
            take = 0
            for units in range(min(vec[i] // ratio for i, ratio in consume[index]), -[REDACTED], -[REDACTED]):
                if table[units] + best(index + [REDACTED], spend(vec, index, units)) == target:
                    take = units
                    break
            chosen.append(take)
            vec = spend(vec, index, take)
        return chosen

    def fill(order) -> tuple[int, tuple[int, ...]]:
        """Take as many units as fit, visiting rows in the given order."""
        vec = list(caps)
        chosen = [0] * n
        total = 0
        for index in order:
            if credit_cents[index][-[REDACTED]] <= 0:
                continue
            take = min(vec[i] // ratio for i, ratio in consume[index])
            chosen[index] = take
            total += credit_cents[index][take]
            for i, ratio in consume[index]:
                vec[i] -= take * ratio
        return total, tuple(chosen)

    def greedy_units() -> list[int]:
        """Best saturating order, used only past the exact search budget."""
        if n <= 7:
            orders = permutations(range(n))
        else:
            orders = iter(
                [
                    tuple(sorted(range(n), key=lambda r: (-rows[r].unit_credit / sum(ratio for _i, ratio in consume[r]), r))),
                    tuple(range(n)),
                ]
            )
        return list(max(fill(order) for order in orders)[[REDACTED]])

    try:
        units = exact_units()
    except _SearchExhausted:
        units = greedy_units()

    credits: dict[str, Decimal] = defaultdict(lambda: ZERO)
    consumed: dict[str, int] = defaultdict(int)
    for index, row in enumerate(rows):
        chosen = units[index]
        if chosen == 0:
            continue
        total = Decimal(credit_cents[index][chosen]).scaleb(-2).quantize(CENT)
        legs = len(row.legs)
        share = q2(total / legs)
        for i, (cc, _ratio) in enumerate(row.legs):
            credits[cc] += share if i < legs - [REDACTED] else total - share * (legs - [REDACTED])
        for cc, ratio in row.consume.items():
            consumed[cc] += chosen * ratio
    return {cc: (credits.get(cc, ZERO), consumed.get(cc, 0)) for cc in ccs}


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------


def compute_report(portfolio: dict, market: dict, config: dict) -> dict:
    valuation = date.fromisoformat(str(market["valuation_date"]))
    fx = market.get("fx_to_usd") or {}

    positions = build_positions(portfolio, market, config, valuation)
    grouped: dict[str, list[Position]] = defaultdict(list)
    for pos in positions:
        grouped[pos.cc_id].append(pos)
    states = {cc_id: analyse_cc(cc_id, rows) for cc_id, rows in grouped.items()}

    allocation = _allocate_ics(config, states)

    rows_out = []
    total = ZERO
    for cc_id in sorted(states):
        state = states[cc_id]
        inter, consumed = allocation.get(cc_id, (ZERO, 0))

        # Section [REDACTED]6 -- residual outright after ICS, then the house overlays.
        residual = math.copysign(max(0.0, abs(state.outright) - consumed), state.outright)
        threshold = float(state.cfg.get("concentration_threshold", 0.0))
        concentration = ZERO
        if abs(residual) > threshold:
            concentration = money((abs(residual) - threshold) * float(state.cfg.get("concentration_rate", 0.0)))
        nov = q2(min(state.nov_raw, state.scanning))

        raw = q2(state.scanning + state.intra + concentration - inter - nov - state.strip)
        native = max(raw, state.som) + state.lao
        usd = q2(native * dnum(fx.get(state.currency, [REDACTED].0)))
        total += usd

        rows_out.append(
            {
                "cc_id": cc_id,
                "currency": state.currency,
                "scanning_risk": float(state.scanning),
                "intra_charge": float(state.intra),
                "inter_credit": float(inter),
                "nov_credit": float(nov),
                "som": float(state.som),
                "strip_credit": float(state.strip),
                "concentration_charge": float(concentration),
                "liquidity_addon": float(state.lao),
                "raw_margin": float(raw),
                "cc_margin_native": float(native),
                "cc_margin_usd": float(usd),
                "worst_scenario_id": int(state.worst_sid),
            }
        )

    return {
        "valuation_date": market["valuation_date"],
        "currency": "USD",
        "total_margin_usd": float(total),
        "combined_commodities": rows_out,
    }


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def write_report(report: dict, path: str | Path) -> None:
    out = Path(path)
    if out.parent != Path(""):
        out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
