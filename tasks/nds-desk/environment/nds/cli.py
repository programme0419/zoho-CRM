from __future__ import annotations

import argparse
import json
from pathlib import Path

from .adjust import adjust
from .calendar import Calendar
from .accrue import accrue
from .dates import parse_iso
from .schedule import build_schedule
from .tenor import add_tenor


def run_job(job: dict, cal_dir: Path | None = None) -> dict:
    op = job["op"]
    jid = job["id"]
    if op == "adjust":
        cal = Calendar.load(job["cal"], cal_dir)
        d = parse_iso(job["date"])
        out = adjust(d, cal, job["conv"], eom_from=parse_iso(job["date"]))
        return {"id": jid, "date": out.isoformat()}
    if op == "add_tenor":
        cal = Calendar.load(job["cal"], cal_dir)
        d = parse_iso(job["date"])
        out = add_tenor(d, job["tenor"], cal, job.get("conv", "U"))
        return {"id": jid, "date": out.isoformat()}
    if op == "accrue":
        rec = accrue(
            parse_iso(job["start"]),
            parse_iso(job["end"]),
            job["notional"],
            job["rate"],
            job["dcc"],
        )
        rec["id"] = jid
        return rec
    if op == "schedule":
        cal = Calendar.load(job["cal"], cal_dir)
        periods = build_schedule(
            parse_iso(job["effective"]),
            parse_iso(job["terminate"]),
            job["freq"],
            cal,
            job.get("conv", "MF"),
            job.get("stub", "SHORT_FRONT"),
            job["dcc"],
            job["notional"],
            job["rate"],
        )
        return {"id": jid, "periods": periods}
    raise ValueError(f"unknown op {op}")


def run_batch(batch: dict, cal_dir: Path | None = None) -> dict:
    return {"results": [run_job(job, cal_dir) for job in batch["jobs"]]}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--batch", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args(argv)
    batch = json.loads(Path(args.batch).read_text())
    out = run_batch(batch)
    Path(args.output).write_text(json.dumps(out, indent=2) + "\n")
    return 0
