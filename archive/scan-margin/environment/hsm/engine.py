"""House Scan Margin engine.

Computes per-combined-commodity scanning risk from the 16 HSM price/vol
scenarios and assembles the margin report.
"""

from __future__ import annotations

import json
from collections import defaultdict
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Any

CENT = Decimal("0.01")

# Price multipliers for the 16 HSM scenarios (ids 1-16).
PRICE_MULT = [0, 0, 1 / 3, 1 / 3, -1 / 3, -1 / 3, 2 / 3, 2 / 3, -2 / 3, -2 / 3, 1, 1, -1, -1, 3, -3]


def q2(x: Decimal) -> Decimal:
    return Decimal(x).quantize(CENT, rounding=ROUND_HALF_EVEN)


def money(x: float) -> Decimal:
    return Decimal(format(float(x), ".10f")).quantize(CENT, rounding=ROUND_HALF_EVEN)


def net_positions(portfolio: dict) -> dict[str, float]:
    qty: dict[str, float] = defaultdict(float)
    for row in portfolio["positions"]:
        qty[row["instrument_id"]] += float(row["qty"])
    return {k: v for k, v in qty.items() if v != 0.0}


def product_of(instrument_id: str) -> str:
    return instrument_id.split("-")[0]


def is_option(instrument_id: str) -> bool:
    parts = instrument_id.split("-")
    return len(parts) >= 5 and parts[3] in ("C", "P")


def compute_report(portfolio: dict, market: dict, config: dict) -> dict:
    net = net_positions(portfolio)
    products = config["products"]
    fx = {k: Decimal(str(v)) for k, v in market["fx_to_usd"].items()}

    by_cc: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for iid, qty in net.items():
        prod = product_of(iid)
        cc = products[prod]["cc_id"]
        by_cc[cc].append((iid, qty))

    rows = []
    total = Decimal("0.00")
    for cc_id in sorted(by_cc):
        iids = by_cc[cc_id]
        prod_name = product_of(iids[0][0])
        prod = products[prod_name]
        psr = float(prod["price_scan_range"])
        mult = float(prod["multiplier"])
        ccy = prod["currency"]

        # Scenario P/L from futures linear shocks. Options are priced at
        # unchanged value (zero P/L) because they are marked futures-style.
        cc_pl = []
        for sid in range(1, 17):
            m = PRICE_MULT[sid - 1]
            w = 0.28 if sid >= 15 else 1.0
            pl = Decimal("0.00")
            for iid, qty in iids:
                if is_option(iid):
                    continue
                pl += money(qty * m * psr * mult * w)
            cc_pl.append((sid, pl))

        worst_sid, worst_pl = min(cc_pl, key=lambda t: (t[1], t[0]))
        scan = q2(max(Decimal("0"), -worst_pl))
        intra = Decimal("0.00")
        inter = Decimal("0.00")
        nov = Decimal("0.00")
        som = Decimal("0.00")
        raw = q2(scan + intra - inter - nov)
        native = max(raw, som)
        usd = q2(native * fx[ccy])
        total += usd
        rows.append(
            {
                "cc_id": cc_id,
                "currency": ccy,
                "scanning_risk": float(scan),
                "intra_charge": float(intra),
                "inter_credit": float(inter),
                "nov_credit": float(nov),
                "som": float(som),
                "raw_margin": float(raw),
                "cc_margin_native": float(native),
                "cc_margin_usd": float(usd),
                "worst_scenario_id": int(worst_sid),
            }
        )

    return {
        "valuation_date": market["valuation_date"],
        "currency": "USD",
        "total_margin_usd": float(total),
        "combined_commodities": rows,
    }


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def write_report(report: dict, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(report, indent=2) + "\n")
