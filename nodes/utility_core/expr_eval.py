"""Safe arithmetic expression evaluator for Duration -> Frames.

A whitelisted AST walk: nothing is ever passed to eval/exec/compile-for-exec.
"""
from __future__ import annotations

import ast
import math
import operator
from collections.abc import Callable, Mapping
from typing import Union

Number = Union[int, float, bool]

MAX_LEN = 300
MAX_NODES = 200
MAX_EXPONENT = 64
MAX_INT_BITS = 256
MAX_ARGS = 3
MAX_ROUND_DIGITS = 32
MAX_FRAMES = 1_000_000


class ExprError(ValueError):
    """A user-facing evaluation error."""


def _round(x: Number, nd: Number | None = None) -> Number:
    if nd is None:
        return round(x)
    digits = int(nd)  # raises OverflowError / ValueError for inf / nan; both are reported as errors
    if abs(digits) > MAX_ROUND_DIGITS:
        raise ExprError(f"round() digits out of range (|digits| > {MAX_ROUND_DIGITS})")
    return round(x, digits)


FUNCS: dict[str, Callable[..., Number]] = {
    "max": max, "min": min, "round": _round, "abs": abs,
    "ceil": math.ceil, "floor": math.floor, "int": int, "float": float, "sqrt": math.sqrt,
}
CONSTANTS: dict[str, float] = {"pi": math.pi, "e": math.e}
VARIABLES = ("a", "fps")

_BINOPS: dict[type[ast.operator], Callable[[Number, Number], Number]] = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_CMPOPS: dict[type[ast.cmpop], Callable[[Number, Number], bool]] = {
    ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
    ast.Eq: operator.eq, ast.NotEq: operator.ne,
}


def _check(v: object) -> Number:
    if isinstance(v, complex):
        raise ExprError("complex results are not allowed")
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        if v.bit_length() > MAX_INT_BITS:
            raise ExprError(f"integer too large (over {MAX_INT_BITS} bits)")
        return v
    if isinstance(v, float):
        return v
    raise ExprError(f"unsupported value type: {type(v).__name__}")


class _Evaluator:
    def __init__(self, env: Mapping[str, Number]) -> None:
        self.env = env
        self.visited = 0

    def visit(self, node: ast.AST) -> Number:
        self.visited += 1
        if self.visited > MAX_NODES:
            raise ExprError(f"expression too complex (over {MAX_NODES} nodes)")
        if isinstance(node, ast.Expression):
            return self.visit(node.body)
        if isinstance(node, ast.Constant):
            v = node.value
            if isinstance(v, (bool, int, float)) and not isinstance(v, complex):
                return _check(v)
            raise ExprError("only numeric literals are allowed")
        if isinstance(node, ast.Name):
            if node.id in self.env:
                return self.env[node.id]
            if node.id in CONSTANTS:
                return CONSTANTS[node.id]
            raise ExprError(f"unknown name '{node.id}'")
        if isinstance(node, ast.UnaryOp):
            v = self.visit(node.operand)
            if isinstance(node.op, ast.UAdd):
                return _check(+v)
            if isinstance(node.op, ast.USub):
                return _check(-v)
            if isinstance(node.op, ast.Not):
                return not v
            raise ExprError("unsupported unary operator")
        if isinstance(node, ast.BinOp):
            fn = _BINOPS.get(type(node.op))
            if fn is None:
                raise ExprError("unsupported operator")
            left, right = self.visit(node.left), self.visit(node.right)
            if isinstance(node.op, ast.Pow):
                self._check_pow(left, right)
            return _check(fn(left, right))
        if isinstance(node, ast.Compare):
            left = self.visit(node.left)
            for op, comp in zip(node.ops, node.comparators):
                cmp = _CMPOPS.get(type(op))
                if cmp is None:
                    raise ExprError("unsupported comparison")
                right = self.visit(comp)
                if not cmp(left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.BoolOp):
            vals = [self.visit(v) for v in node.values]
            if isinstance(node.op, ast.And):
                return all(vals)
            return any(vals)
        if isinstance(node, ast.IfExp):
            return self.visit(node.body) if self.visit(node.test) else self.visit(node.orelse)
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCS:
                name = node.func.id if isinstance(node.func, ast.Name) else "?"
                raise ExprError(f"unknown function '{name}'")
            if node.keywords:
                raise ExprError("keyword arguments are not allowed")
            if any(isinstance(a, ast.Starred) for a in node.args):
                raise ExprError("starred arguments are not allowed")
            if len(node.args) > MAX_ARGS:
                raise ExprError(f"too many arguments (max {MAX_ARGS})")
            args = [self.visit(a) for a in node.args]
            return _check(FUNCS[node.func.id](*args))
        raise ExprError(f"unsupported syntax: {type(node).__name__}")

    @staticmethod
    def _check_pow(base: Number, exp: Number) -> None:
        if abs(exp) > MAX_EXPONENT:
            raise ExprError(f"exponent too large (|exponent| > {MAX_EXPONENT})")
        if isinstance(base, int) and isinstance(exp, int) and exp > 0:
            if abs(int(base)).bit_length() * int(exp) > MAX_INT_BITS:
                raise ExprError(f"power result too large (over {MAX_INT_BITS} bits)")


def evaluate(expression: str, a: float, fps: float) -> Number:
    expr = (expression or "").strip()
    if not expr:
        raise ExprError("expression is empty")
    if len(expr) > MAX_LEN:
        raise ExprError(f"expression too long (max {MAX_LEN} characters)")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ExprError(f"syntax error: {exc.msg}") from None
    except (RecursionError, MemoryError, ValueError):
        raise ExprError("expression too deeply nested") from None
    try:
        return _Evaluator({"a": a, "fps": fps}).visit(tree)
    except ExprError:
        raise
    except ZeroDivisionError:
        raise ExprError("division by zero") from None
    except (OverflowError, RecursionError, MemoryError):
        raise ExprError("numeric overflow or expression too deeply nested") from None
    except (ValueError, TypeError, ArithmeticError) as exc:
        raise ExprError(f"math error: {exc}") from None


def to_frames(expression: str, a: float, fps: float) -> int:
    v = evaluate(expression, a, fps)
    if isinstance(v, float):
        if not math.isfinite(v):
            raise ExprError("result is not a finite number")
        v = round(v)
    n = int(v)
    if n > MAX_FRAMES:
        raise ExprError(f"result too large (over {MAX_FRAMES:,} frames)")
    return max(1, n)
