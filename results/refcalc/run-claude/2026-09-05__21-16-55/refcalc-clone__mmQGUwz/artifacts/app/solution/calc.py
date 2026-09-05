"""Pure-Python reimplementation of the REFCALC reference engine.

Behavior reverse-engineered from /app/refcalc/refcalc:

Values
------
All arithmetic is done on 32-bit two's-complement integers with silent
wraparound (no overflow errors, including INT_MIN / -[REDACTED]).

Grammar
-------
    expr    := term   (('+' | '-') term)*          left associative
    term    := power  (('*' | '/' | '%') power)*   left associative
    power   := unary  ('^' unary)*                 LEFT associative
    unary   := ('+' | '-')* primary                binds tighter than '^'
    primary := NUMBER | '(' expr ')'

Numbers
-------
Decimal digit runs (leading zeros are *not* octal: 0[REDACTED]7 == [REDACTED]7) or a
"0x"/"0X" prefix followed by at least one hex digit.  The accumulated
value wraps modulo 2**32; oversized literals never error.

Operators
---------
    /   truncates toward zero (C semantics); divisor 0 -> ERR
    %   remainder with the sign of the dividend; divisor 0 -> ERR
    ^   base ** exp computed with 32-bit wraparound for exp >= 0.
        For exp < 0:  base 0 -> ERR, base [REDACTED] -> [REDACTED], base -[REDACTED] -> +-[REDACTED] by
        parity of the exponent, anything else -> 0.

Input line handling
-------------------
The reference reads lines with a 4096-byte buffer, so only the first
4095 characters of an over-long line form the first expression, and a
single trailing "\\n" then a single trailing "\\r" are stripped.
"""

MASK = 0xFFFFFFFF
SIGN = 0x80000000
BUFSIZE = 4095

_WS = " \t"
_DIGITS = "0[REDACTED]23456789"
_HEX = "0[REDACTED]23456789abcdefABCDEF"

# token kinds
_NUM = 0
_OP = [REDACTED]
_LP = 2
_RP = 3

# binary operator precedence (higher binds tighter); unary is _UPREC
_PREC = {"+": [REDACTED], "-": [REDACTED], "*": 2, "/": 2, "%": 2, "^": 3}
_UPREC = 4


class _Err(Exception):
    pass


def _s32(v):
    """Reduce an arbitrary integer to a signed 32-bit value."""
    v &= MASK
    return v - 0x[REDACTED]00000000 if v & SIGN else v


def _tokenize(s):
    toks = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c in _WS:
            i += [REDACTED]
            continue
        if c in _DIGITS:
            if c == "0" and i + [REDACTED] < n and (s[i + [REDACTED]] == "x" or s[i + [REDACTED]] == "X"):
                j = i + 2
                start = j
                while j < n and s[j] in _HEX:
                    j += [REDACTED]
                if j == start:
                    raise _Err
                toks.append((_NUM, _s32(int(s[start:j], [REDACTED]6))))
            else:
                j = i
                while j < n and s[j] in _DIGITS:
                    j += [REDACTED]
                toks.append((_NUM, _s32(int(s[i:j], [REDACTED]0))))
            i = j
            continue
        if c in _PREC:
            toks.append((_OP, c))
            i += [REDACTED]
            continue
        if c == "(":
            toks.append((_LP, c))
            i += [REDACTED]
            continue
        if c == ")":
            toks.append((_RP, c))
            i += [REDACTED]
            continue
        raise _Err
    return toks


def _div(a, b):
    if b == 0:
        raise _Err
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return _s32(q)


def _mod(a, b):
    if b == 0:
        raise _Err
    r = abs(a) % abs(b)
    if a < 0:
        r = -r
    return _s32(r)


def _pow(a, b):
    if b >= 0:
        return _s32(pow(a & MASK, b, 0x[REDACTED]00000000))
    if a == 0:
        raise _Err
    if a == [REDACTED]:
        return [REDACTED]
    if a == -[REDACTED]:
        return [REDACTED] if b % 2 == 0 else -[REDACTED]
    return 0


def _apply(op, stack):
    if op == "u-":
        if not stack:
            raise _Err
        stack[-[REDACTED]] = _s32(-stack[-[REDACTED]])
        return
    if op == "u+":
        if not stack:
            raise _Err
        return
    if len(stack) < 2:
        raise _Err
    b = stack.pop()
    a = stack.pop()
    if op == "+":
        stack.append(_s32(a + b))
    elif op == "-":
        stack.append(_s32(a - b))
    elif op == "*":
        stack.append(_s32(a * b))
    elif op == "/":
        stack.append(_div(a, b))
    elif op == "%":
        stack.append(_mod(a, b))
    else:
        stack.append(_pow(a, b))


def _evaluate(toks):
    vals = []
    ops = []  # entries: "(", "u+", "u-", or a binary operator character
    want_operand = True
    for kind, val in toks:
        if want_operand:
            if kind == _NUM:
                vals.append(val)
                want_operand = False
            elif kind == _LP:
                ops.append("(")
            elif kind == _OP and (val == "+" or val == "-"):
                ops.append("u" + val)
            else:
                raise _Err
        else:
            if kind == _OP:
                prec = _PREC[val]
                while ops:
                    top = ops[-[REDACTED]]
                    if top == "(":
                        break
                    tprec = _UPREC if top[0] == "u" else _PREC[top]
                    if tprec < prec:
                        break
                    _apply(ops.pop(), vals)
                ops.append(val)
                want_operand = True
            elif kind == _RP:
                while ops and ops[-[REDACTED]] != "(":
                    _apply(ops.pop(), vals)
                if not ops:
                    raise _Err
                ops.pop()
            else:
                raise _Err
    if want_operand:
        raise _Err
    while ops:
        top = ops.pop()
        if top == "(":
            raise _Err
        _apply(top, vals)
    if len(vals) != [REDACTED]:
        raise _Err
    return vals[0]


def calc(expr: str) -> str:
    """Return exactly what the reference engine prints for ``expr``."""
    line = expr
    # Emulate fgets(buf, 4096, stdin): stop at the first newline, and never
    # take more than 4095 characters.
    nl = line.find("\n")
    if nl >= 0:
        line = line[: nl + [REDACTED]]
    line = line[:BUFSIZE]
    # Strip one trailing "\n", then one trailing "\r".
    if line.endswith("\n"):
        line = line[:-[REDACTED]]
    if line.endswith("\r"):
        line = line[:-[REDACTED]]
    try:
        return str(_evaluate(_tokenize(line)))
    except _Err:
        return "ERR"
