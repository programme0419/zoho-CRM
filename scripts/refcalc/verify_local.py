"""Local grading matrix for refcalc-clone (no Docker needed).

Runs each candidate calc.py over the hidden corpus and reports match counts,
mirroring the verifier. Also runs the anti-cheat grep against each candidate.
"""
import importlib.util
import json
import os
import re
import signal
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
TASK = os.path.join(ROOT, "tasks", "refcalc-clone")
EXPECTED = json.load(open(os.path.join(TASK, "tests", "expected.json")))["cases"]

CHEAT_RE = re.compile(
    r"(\bsubprocess\b|os\.system|os\.popen|os\.exec|multiprocessing|"
    r"\bctypes\b|\bsocket\b|__import__)"
)

CANDIDATES = {
    "solution": os.path.join(TASK, "solution", "calc.py"),
    "stub": os.path.join(TASK, "environment", "solution_stub", "calc.py"),
    "naive-standard": os.path.join(HERE, "naive_calc.py"),
}


def load_calc(path):
    spec = importlib.util.spec_from_file_location("cand_calc", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.calc


def grade(path):
    src = open(path).read()
    cheat = bool(CHEAT_RE.search(src))
    try:
        calc = load_calc(path)
    except Exception as exc:  # noqa: BLE001
        return {"cheat": cheat, "loaded": False, "err": repr(exc)}
    match = 0
    fails = []

    class _TO(Exception):
        pass

    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(_TO()))
    for c in EXPECTED:
        signal.setitimer(signal.ITIMER_REAL, 5.0)
        try:
            got = calc(c["expr"])
        except _TO:
            got = "<timeout>"
        except Exception as exc:  # noqa: BLE001
            got = f"<exc:{type(exc).__name__}>"
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0.0)
        if got == c["expected"]:
            match += 1
        elif len(fails) < 8:
            fails.append((c["expr"], c["expected"], got))
    return {
        "cheat": cheat,
        "loaded": True,
        "match": match,
        "total": len(EXPECTED),
        "fails": fails,
    }


def main():
    rc = 0
    for name, path in CANDIDATES.items():
        r = grade(path)
        print(f"\n=== {name} ===  cheat_flagged={r['cheat']}")
        if not r.get("loaded"):
            print(f"  load failed: {r['err']}  -> reward 0 (expected for stub)")
            continue
        reward = 1 if r["match"] == r["total"] and not r["cheat"] else 0
        print(f"  matched {r['match']}/{r['total']}  -> reward {reward}")
        for e, exp, got in r["fails"]:
            print(f"    DIFF expr={e!r} ref={exp!r} got={got!r}")
        expected_reward = 1 if name == "solution" else 0
        if reward != expected_reward:
            print(f"  !! UNEXPECTED: {name} reward {reward}, wanted {expected_reward}")
            rc = 1
    print("\nMATRIX", "OK" if rc == 0 else "FAILED")
    sys.exit(rc)


if __name__ == "__main__":
    main()
