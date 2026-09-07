# refcalc-clone

Reverse-engineer a black-box integer-expression engine and reimplement it
exactly in pure Python.

## What the agent is given

- `/app/refcalc/refcalc` — a stripped, statically linked reference engine. It
  reads one expression per line from stdin and prints the result (a signed
  decimal integer) or `ERR`. There is no source and no written specification.
- `/app/refcalc/README.md` — the contract and output format.
- `/app/solution/calc.py` — a stub to replace with the reimplementation.

## The deliverable

`/app/solution/calc.py` defining `calc(expr: str) -> str`, returning exactly
what the reference prints. It must be self-contained pure Python (no shelling
out, no loading the reference, no `subprocess`/`ctypes`/`socket`/`eval`/`exec`).

## Why it is hard

The engine's semantics are internally consistent but deliberately violate common
conventions, and none of them are documented — each must be found by probing:

- `^` is exponentiation, **left-associative**, binding tighter than `* / %`.
- Unary minus binds **tighter** than `^` (`-2^2 == 4`).
- Division truncates toward zero; modulo takes the **dividend's** sign (C rules).
- All arithmetic wraps in **signed 32-bit two's complement**.
- Negative exponent → `0` (except bases `1`/`-1`); `0^0 == 1`; `0^-1 == ERR`.
- Divide/modulo by zero → `ERR`; literals are decimal (leading zeros allowed) or
  `0x` hex and themselves wrap mod 2^32; malformed input → `ERR`.

An agent that assumes standard precedence, right-associative powers, Python
division, or big integers passes the easy cases and fails the revealing ones.

## Difficulty explanation

Legacy-clone reverse-engineering from black-box probing alone, against semantics
engineered to defeat strong priors. Partial recovery is not enough: all 419
hidden expressions must match.

## Solution explanation

A recursive-descent evaluator whose grammar and 32-bit integer semantics mirror
the binary exactly, cross-checked against the compiled reference on 60k+ random
expressions with zero mismatches.

## Verification explanation

A separate verifier copies only `calc.py`, statically rejects cheats, deletes
the reference binary, and runs the agent's `calc()` unprivileged over 419 hidden
expressions (every quirk plus bounded fuzz). Reward is 1 only if all match.

## Relevant experience

Software engineer who reverse-engineers and reimplements underspecified
calculation engines and builds deterministic evaluation harnesses. The engine's
semantics were designed to be internally consistent and fully recoverable by
black-box probing, then implemented and cross-validated against a compiled
reference on 60k+ random expressions.

## Local development

```bash
# build + probe the reference
docker build -t refcalc-env tasks/refcalc-clone/environment
echo '2^3^2' | docker run -i --rm refcalc-env /app/refcalc/refcalc

# regenerate the hidden corpus (after any semantics change)
python3 scripts/refcalc/gen_expected.py

# local verifier matrix (solution=1, naive standard calc=0, stub/nop=0)
bash scripts/refcalc/verify_local.sh
```
