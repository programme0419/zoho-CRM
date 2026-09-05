"""Generate the hidden grading corpus tests/expected.json for refcalc-clone.

Expected outputs are computed by the verified reference (solution/calc.py, which
is bit-identical to the compiled reference on 60k+ fuzz cases). The corpus is a
curated set that isolates every house quirk, plus bounded random fuzz.
"""
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SOL = os.path.join(HERE, "..", "..", "tasks", "refcalc-clone", "solution")
sys.path.insert(0, SOL)
from calc import calc  # noqa: E402

curated = [
    # precedence & left-assoc of + - * / %
    "2+3*4", "2*3+4", "(2+3)*4", "2+3-4", "10-2-3", "8/2/2", "8-2*3",
    "100-10-1", "2*3*4", "20/4/5", "1+2+3+4+5", "7-3+2",
    # power: LEFT associative, higher precedence than * /
    "2^3^2", "2^2^3", "3^2^2", "2^3*2", "2*2^3", "2+2^3", "2^1^0",
    "10^2", "5^3", "2^10", "1^1000", "2^0^5",
    # unary binds tighter than ^
    "-2^2", "-3^2", "-2^3", "-(2^2)", "(-2)^2", "(-2)^3",
    "--2", "-+-2", "+-+3", "---5", "-2^-2", "2^-1", "2^-2",
    # C truncated division and dividend-signed modulo
    "7/2", "-7/2", "7/-2", "-7/-2", "7%2", "-7%2", "7%-2", "-7%-2",
    "6/4", "-6/4", "5%3", "-5%3", "5%-3", "-5%-3", "9/10", "-9/10", "1%1",
    # division / modulo by zero and propagation
    "5/0", "5%0", "0/5", "0%5", "(1+2)/(3-3)", "1+5/0", "10%0+1", "1/0*0",
    # power special cases
    "0^0", "0^1", "0^5", "0^-1", "1^-100", "(-1)^-3", "(-1)^-4",
    "1^0", "5^0", "5^-1", "2^0", "(-1)^0", "3^-3",
    # 32-bit two's-complement overflow wrap
    "2^31", "2^32", "2^33", "2^30", "46341^2", "65536*65536",
    "2147483647+1", "0-2147483648-1", "3^20", "1000000*1000000",
    "99999*99999", "2^31-1", "2^31+2^31",
    # hex literals
    "0x10", "0xff", "0xFF", "0X1a", "0x0", "0x100+1", "-0x10",
    "0x7fffffff", "0x80000000", "0xffffffff", "0xdeadbeef", "0xabc+0x4",
    # leading zeros are decimal, not octal
    "007", "010", "0100", "00", "099", "0x0F",
    # whitespace handling
    " 2 + 3 ", "2\t*\t3", "( 2 )", " ( 1 + 2 ) * 3 ", "\t\t9\t",
    # malformed -> ERR
    "", "   ", "2 3", "2+", "*2", "()", "(2", "2)", "2^", "/2", "%2",
    "1.5", "1e3", "abc", "2**3", "2 2", "0x", "0x1g", "+", "-", "2++3",
    "2--3", "2*-3", "2+-3", "(", ")", "3 4 5", "^2",
    # big literal wrap
    "9999999999", "4294967296", "4294967297", "10000000000", "12345678901",
    # deeper combinations
    "((2+3)*(4-1))^2", "2^3+4^2", "100/7%3", "2^2^2^2", "-1^100",
    "(1+2*3-4/2)^2", "5-3^2", "3^2-5", "10%3^2", "2*3^2%4",
    "-(3^2)+(-3)^2", "((((1))))", "0x10*2^4", "7%3%2", "2^3%5",
]

seen = {}
for e in curated:
    seen[e] = calc(e)

random.seed(90124)
NUMS = lambda: random.choice([
    str(random.randint(0, 9)),
    str(random.randint(0, 99)),
    str(random.randint(0, 9999)),
    "0x" + format(random.randint(0, 0xFFFF), "x"),
    "0" + str(random.randint(0, 99)),
])
OPS = ["+", "-", "*", "/", "%", "^"]


def gen(depth=0):
    r = random.random()
    if depth > 3 or r < 0.45:
        s = NUMS()
    elif r < 0.62:
        s = "(" + gen(depth + 1) + ")"
    else:
        s = gen(depth + 1) + random.choice(OPS) + gen(depth + 1)
    for _ in range(random.randint(0, 2)):
        s = random.choice(["-", "+"]) + s
    if random.random() < 0.25:
        s = " " + s + " "
    return s


fuzz_added = 0
while fuzz_added < 260:
    e = gen()
    if e in seen:
        continue
    seen[e] = calc(e)
    fuzz_added += 1

cases = [{"expr": e, "expected": seen[e]} for e in sorted(seen, key=lambda k: (len(k), k))]
out = os.path.join(HERE, "..", "..", "tasks", "refcalc-clone", "tests", "expected.json")
with open(out, "w") as f:
    json.dump({"cases": cases}, f, indent=1)
    f.write("\n")

n_err = sum(1 for c in cases if c["expected"] == "ERR")
print(f"wrote {len(cases)} cases ({n_err} ERR) to {out}")
