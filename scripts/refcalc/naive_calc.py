"""A plausible WRONG solution: standard/Pythonic semantics.

Right-associative '^', Python division/modulo, unbounded integers, no wrap.
Represents what a model assuming conventional behavior would produce. Must FAIL.
"""
from __future__ import annotations

import ast
import operator


def calc(expr: str) -> str:
    expr = expr.strip()
    if not expr:
        return "ERR"
    py = expr.replace("^", "**")
    try:
        node = ast.parse(py, mode="eval")
    except SyntaxError:
        return "ERR"

    ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant):
            if not isinstance(n.value, int):
                raise ValueError
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in ops:
            return ops[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp):
            if isinstance(n.op, ast.USub):
                return -ev(n.operand)
            if isinstance(n.op, ast.UAdd):
                return +ev(n.operand)
        raise ValueError

    try:
        return str(ev(node))
    except (ValueError, ZeroDivisionError, TypeError):
        return "ERR"
