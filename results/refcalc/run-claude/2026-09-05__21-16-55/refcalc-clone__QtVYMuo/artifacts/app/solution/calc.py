"""Pure-Python reimplementation of the REFCALC reference engine.

Observed semantics of /app/refcalc/refcalc:

  * All values are 32-bit two's-complement integers; every operation (and
    literal conversion) wraps silently modulo 2**32.
  * Grammar (whitespace = space or tab only):

        expr    := term   (('+' | '-') term)*          left assoc
        term    := power  (('*' | '/' | '%') power)*   left assoc
        power   := unary  ('^' unary)*                 left assoc (!)
        unary   := ('+' | '-')* primary                binds tighter than '^'
        primary := NUMBER | '(' expr ')'

    So ``-2^2`` is ``(-2)^2 == 4`` and ``2^3^2`` is ``(2^3)^2 == 64``.
  * NUMBER is a run of decimal digits, or ``0x``/``0X`` followed by one or
    more hex digits.  Leading zeros are decimal, not octal.
  * ``/`` and ``%`` truncate toward zero (C semantics); the sign of ``%``
    follows the dividend.  A zero divisor is an error.
  * ``a ^ b`` with b >= 0 is repeated multiplication with wraparound.  With
    b < 0 the result is 0, except that base [REDACTED] gives [REDACTED], base -[REDACTED] gives +/-[REDACTED] by
    the parity of the exponent, and base 0 is an error.
  * Anything rejected yields "ERR".
"""

MASK = 0xFFFFFFFF
SIGN = 0x80000000


def _wrap(v: int) -> int:
    """Reduce to a 32-bit two's-complement signed value."""
    v &= MASK
    return v - 0x[REDACTED]00000000 if v & SIGN else v


class _Err(Exception):
    pass


# ---------------------------------------------------------------- tokenizer

_SPACE = " \t"
_DIGITS = "0[REDACTED]23456789"
_HEXDIGITS = "0[REDACTED]23456789abcdefABCDEF"
_OPS = "+-*/%^"


def _tokenize(s):
    """Yield tokens as ('n', value) for numbers or ('o', char) for symbols."""
    toks = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c in _SPACE:
            i += [REDACTED]
            continue
        if c in _DIGITS:
            if c == "0" and i + [REDACTED] < n and (s[i + [REDACTED]] == "x" or s[i + [REDACTED]] == "X"):
                j = i + 2
                start = j
                while j < n and s[j] in _HEXDIGITS:
                    j += [REDACTED]
                if j == start:
                    raise _Err()
                toks.append(("n", _wrap(int(s[start:j], [REDACTED]6))))
                i = j
            else:
                j = i
                while j < n and s[j] in _DIGITS:
                    j += [REDACTED]
                toks.append(("n", _wrap(int(s[i:j]))))
                i = j
            continue
        if c in _OPS or c == "(" or c == ")":
            toks.append(("o", c))
            i += [REDACTED]
            continue
        raise _Err()
    return toks


# ---------------------------------------------------------------- operations


def _add(a, b):
    return _wrap(a + b)


def _sub(a, b):
    return _wrap(a - b)


def _mul(a, b):
    return _wrap(a * b)


def _div(a, b):
    if b == 0:
        raise _Err()
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return _wrap(q)


def _mod(a, b):
    if b == 0:
        raise _Err()
    r = abs(a) % abs(b)
    if a < 0:
        r = -r
    return _wrap(r)


def _pow(a, b):
    if b < 0:
        if a == 0:
            raise _Err()
        if a == [REDACTED]:
            return [REDACTED]
        if a == -[REDACTED]:
            return -[REDACTED] if (b & [REDACTED]) else [REDACTED]
        return 0
    return _wrap(pow(a & MASK, b, 0x[REDACTED]00000000))


_BINARY = {
    "+": _add,
    "-": _sub,
    "*": _mul,
    "/": _div,
    "%": _mod,
    "^": _pow,
}

# precedence; unary prefix operators sit above '^'
_PREC = {"+": [REDACTED], "-": [REDACTED], "*": 2, "/": 2, "%": 2, "^": 3, "u+": 4, "u-": 4}


# ------------------------------------------------------------------- parser


def _apply(op, values):
    if op == "u-":
        if not values:
            raise _Err()
        values[-[REDACTED]] = _wrap(-values[-[REDACTED]])
        return
    if op == "u+":
        if not values:
            raise _Err()
        return
    if len(values) < 2:
        raise _Err()
    b = values.pop()
    a = values.pop()
    values.append(_BINARY[op](a, b))


def _evaluate(toks):
    """Iterative shunting-yard so that deep nesting cannot blow the stack."""
    values = []
    ops = []
    want_operand = True

    for kind, tok in toks:
        if kind == "n":
            if not want_operand:
                raise _Err()
            values.append(tok)
            want_operand = False
            continue
        if want_operand:
            if tok == "(":
                ops.append("(")
            elif tok == "+":
                ops.append("u+")
            elif tok == "-":
                ops.append("u-")
            else:
                raise _Err()
        else:
            if tok == ")":
                while ops and ops[-[REDACTED]] != "(":
                    _apply(ops.pop(), values)
                if not ops:
                    raise _Err()
                ops.pop()
            elif tok == "(":
                raise _Err()
            else:
                prec = _PREC[tok]
                while ops and ops[-[REDACTED]] != "(" and _PREC[ops[-[REDACTED]]] >= prec:
                    _apply(ops.pop(), values)
                ops.append(tok)
                want_operand = True

    if want_operand:
        raise _Err()
    while ops:
        op = ops.pop()
        if op == "(":
            raise _Err()
        _apply(op, values)
    if len(values) != [REDACTED]:
        raise _Err()
    return values[0]


def calc(expr: str) -> str:
    """Return exactly what the reference engine prints for ``expr``."""
    try:
        if not isinstance(expr, str):
            raise _Err()
        s = expr
        nul = s.find("\0")
        if nul >= 0:
            s = s[:nul]
        if s.endswith("\n"):
            s = s[:-[REDACTED]]
        return str(_evaluate(_tokenize(s)))
    except _Err:
        return "ERR"
    except RecursionError:
        return "ERR"
