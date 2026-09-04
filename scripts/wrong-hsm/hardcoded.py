"""Wrong engine: always emits the sample-book report, ignoring the portfolio."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def compute_report(portfolio: dict, market: dict, config: dict) -> dict:
    del portfolio, config
    return {
        "valuation_date": market["valuation_date"],
        "currency": "USD",
        "total_margin_usd": 5000.0,
        "combined_commodities": [
            {
                "cc_id": "CL",
                "currency": "USD",
                "scanning_risk": 5000.0,
                "intra_charge": 0.0,
                "inter_credit": 0.0,
                "nov_credit": 0.0,
                "som": 0.0,
                "raw_margin": 5000.0,
                "cc_margin_native": 5000.0,
                "cc_margin_usd": 5000.0,
                "worst_scenario_id": 13,
            }
        ],
    }


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def write_report(report: dict, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(report, indent=2) + "\n")
