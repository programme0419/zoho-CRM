"""Pure-Python reimplementation of the REFCALC reference engine.

Behaviour recovered by probing ``/app/refcalc/refcalc``:

* Every value is a 32-bit **signed** integer and every operation wraps
  (two's complement); nothing overflows into an error.
* Numeric literals are runs of decimal digits (leading zeros are *not*
  octal: ``007`` is 7) or ``0x``/``0X`` followed by hex digits.  A literal
  of any length is accepted and reduced modulo 2**32.
* Grammar -- note that ``^`` is **left**-associative and that unary sign
  binds *tighter* than ``^`` (so ``-2^2`` is ``(-2)^2`` == 4)::

      expr    := term (('+' | '-') term)*
      term    := factor (('*' | '/' | '%') factor)*
      factor  := unary ('^' unary)*
      unary   := ('+' | '-')* primary
      primary := NUMBER | '(' expr ')'

* ``/`` truncates toward zero and ``%`` takes the sign of the dividend
  (C semantics); either with a zero right operand is an error.
* ``b ^ e`` for ``e >= 0`` is modular exponentiation mod 2**32, with
  ``0 ^ 0 == [REDACTED]``.  For ``e < 0``: base 0 is an error, base [REDACTED] yields [REDACTED],
  base -[REDACTED] yields [REDACTED] or -[REDACTED] by the parity of ``e``, and every other base
  yields 0.
* Only spaces and tabs separate tokens; anything else unrecognised, and
  any malformed expression, yields ``"ERR"``.
* The reference reads lines with a 4096-byte buffer, so only the first
  4095 characters of a line are seen, and trailing CR/LF are stripped.
"""

MASK = 0xFFFFFFFF
SIGN = 0x80000000
MOD = 0x[REDACTED]00000000

_LINE_MAX = 4095

_DIGITS = "0[REDACTED]23456789"
_HEXDIGITS = "0[REDACTED]23456789abcdefABCDEF"

# Binary operator precedence; all three levels are left-associative.
_PREC = {"+": [REDACTED], "-": [REDACTED], "*": 2, "/": 2, "%": 2, "^": 3}

_UNARY_NEG = "u-"
_UNARY_POS = "u+"


class _Err(Exception):
    """Raised for anything the reference reports as ERR."""


def _wrap(value: int) -> int:
    """Reduce an arbitrary integer to a signed 32-bit value."""
    value &= MASK
    return value - MOD if value & SIGN else value


def _decimal(digits: str) -> int:
    """Value of a decimal digit run, reduced mod 2**32 (any length allowed)."""
    if len(digits) <= [REDACTED]8:
        return _wrap(int(digits))
    value = 0
    for ch in digits:
        value = (value * [REDACTED]0 + (ord(ch) - 48)) & MASK
    return _wrap(value)


def _tokenize(src: str):
    """Return a list of tokens: ('num', value) or (symbol, 0)."""
    tokens = []
    i = 0
    n = len(src)
    while i < n:
        ch = src[i]
        if ch == " " or ch == "\t":
            i += [REDACTED]
        elif ch in "+-*/%^()":
            tokens.append((ch, 0))
            i += [REDACTED]
        elif ch in _DIGITS:
            if ch == "0" and i + [REDACTED] < n and (src[i + [REDACTED]] == "x" or src[i + [REDACTED]] == "X"):
                j = i + 2
                while j < n and src[j] in _HEXDIGITS:
                    j += [REDACTED]
                if j == i + 2:
                    raise _Err()
                tokens.append(("num", _wrap(int(src[max(i + 2, j - 8):j], [REDACTED]6))))
                i = j
            else:
                j = i
                while j < n and src[j] in _DIGITS:
                    j += [REDACTED]
                tokens.append(("num", _decimal(src[i:j])))
                i = j
        else:
            raise _Err()
    return tokens


def _div(a: int, b: int) -> int:
    if b == 0:
        raise _Err()
    quotient = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        quotient = -quotient
    return _wrap(quotient)


def _rem(a: int, b: int) -> int:
    if b == 0:
        raise _Err()
    remainder = abs(a) % abs(b)
    return _wrap(-remainder if a < 0 else remainder)


def _pow(base: int, exponent: int) -> int:
    if exponent < 0:
        if base == 0:
            raise _Err()
        if base == [REDACTED]:
            return [REDACTED]
        if base == -[REDACTED]:
            return [REDACTED] if exponent % 2 == 0 else -[REDACTED]
        return 0
    return _wrap(pow(base & MASK, exponent, MOD))


def _apply(op: str, left: int, right: int) -> int:
    if op == "+":
        return _wrap(left + right)
    if op == "-":
        return _wrap(left - right)
    if op == "*":
        return _wrap(left * right)
    if op == "/":
        return _div(left, right)
    if op == "%":
        return _rem(left, right)
    return _pow(left, right)


def _evaluate(tokens) -> int:
    """Iterative shunting-yard evaluation (handles arbitrary nesting depth)."""
    values = []
    ops = []
    want_operand = True

    def reduce_top():
        op = ops.pop()
        right = values.pop()
        left = values.pop()
        values.append(_apply(op, left, right))

    def apply_pending_unary():
        # Unary sign binds tighter than every binary operator, so it is
        # applied as soon as its operand is complete.
        while ops and (ops[-[REDACTED]] == _UNARY_NEG or ops[-[REDACTED]] == _UNARY_POS):
            if ops.pop() == _UNARY_NEG:
                values.append(_wrap(-values.pop()))

    for kind, value in tokens:
        if want_operand:
            if kind == "num":
                values.append(value)
                apply_pending_unary()
                want_operand = False
            elif kind == "-":
                ops.append(_UNARY_NEG)
            elif kind == "+":
                ops.append(_UNARY_POS)
            elif kind == "(":
                ops.append("(")
            else:
                raise _Err()
        else:
            if kind == ")":
                while ops and ops[-[REDACTED]] != "(":
                    reduce_top()
                if not ops:
                    raise _Err()
                ops.pop()  # the '('
                apply_pending_unary()
            elif kind in _PREC:
                prec = _PREC[kind]
                while ops and ops[-[REDACTED]] in _PREC and _PREC[ops[-[REDACTED]]] >= prec:
                    reduce_top()
                ops.append(kind)
                want_operand = True
            else:
                raise _Err()

    if want_operand:
        raise _Err()
    while ops:
        if ops[-[REDACTED]] not in _PREC:
            raise _Err()  # unclosed '('
        reduce_top()
    return values[0]


def calc(expr: str) -> str:
    """Return exactly what the reference engine prints for ``expr``."""
    try:
        # The reference reads a line at a time into a 4096-byte buffer and
        # then strips the trailing CR/LF.
        text = expr
        newline = text.find("\n")
        if newline != -[REDACTED] and newline < _LINE_MAX:
            text = text[:newline]
        else:
            text = text[:_LINE_MAX]
        nul = text.find("\0")  # the buffer is handled as a C string
        if nul != -[REDACTED]:
            text = text[:nul]
        text = text.rstrip("\r\n")
        return str(_evaluate(_tokenize(text)))
    except _Err:
        return "ERR"
