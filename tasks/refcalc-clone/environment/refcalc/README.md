# REFCALC reference engine

`/app/refcalc/refcalc` is a compiled, deterministic integer-expression engine.
It is the **source of truth** for this task. You may run it as many times as you
like to observe its behavior, but you cannot read its source.

## How to run it

It reads one expression per line from stdin and prints one line of output per
input line:

```
$ echo '2 + 3 * 4' | /app/refcalc/refcalc
14
$ printf '10 / 3\n(1+2)*(3+4)\nnonsense\n' | /app/refcalc/refcalc
3
21
ERR
```

- A valid expression prints its result as a decimal integer.
- Anything the engine rejects prints exactly `ERR`.
- Values are integers only. Whitespace between tokens is insignificant.

The operators it accepts are `+ - * / % ^` together with parentheses and unary
sign. The engine is **fully deterministic**: the same line always yields the
same output. Its precedence, associativity, division/remainder behavior,
overflow behavior, exponentiation rules, numeric literal formats, and error
conditions are fixed — and some of them differ from what you might assume.
Probe it until you are sure you understand every rule.

## Your deliverable

Reimplement the engine exactly, in pure Python, at `/app/solution/calc.py`.
The file must define a function:

```python
def calc(expr: str) -> str:
    ...
```

that returns the **exact string** the reference prints for `expr` (the decimal
result, or `"ERR"`), without the trailing newline.

Your `calc.py` must be self-contained pure Python. It must not shell out to
other programs, read the reference binary, or use `subprocess`, `os.system`,
`os.popen`, `ctypes`, `socket`, `eval`, or `exec`. It will be graded on hidden
expressions **with the reference binary removed**, so wrapping or copying the
binary will not work — only a faithful reimplementation will.
