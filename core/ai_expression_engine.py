"""Safe expression evaluator for AI-proposed quantitative questions.

Gemini may propose a mathematical structure, but it never executes code. The
expression is parsed into a tiny arithmetic DSL and evaluated independently by
two engines before a question can enter the validated pool.
"""
from __future__ import annotations
import ast
from decimal import Decimal, getcontext

getcontext().prec = 28
_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)
_ALLOWED_UNARY = (ast.UAdd, ast.USub)


def _tree(expression: str) -> ast.Expression:
    if len(expression) > 240:
        raise ValueError("expression too long")
    tree = ast.parse(expression, mode="eval")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Call, ast.Attribute, ast.Subscript, ast.List, ast.Dict, ast.Tuple, ast.Lambda)):
            raise ValueError("unsupported expression construct")
        if isinstance(node, ast.BinOp) and not isinstance(node.op, _ALLOWED_BINOPS):
            raise ValueError("unsupported operator")
        if isinstance(node, ast.UnaryOp) and not isinstance(node.op, _ALLOWED_UNARY):
            raise ValueError("unsupported unary operator")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            raise ValueError("only numeric constants are allowed")
    return tree


def referenced_names(expression: str) -> set[str]:
    return {n.id for n in ast.walk(_tree(expression)) if isinstance(n, ast.Name)}


def operation_count(expression: str) -> int:
    return sum(isinstance(n, (ast.BinOp, ast.UnaryOp)) for n in ast.walk(_tree(expression)))


def structure_signature(expression: str) -> str:
    """Ignore concrete values/names; retain the mathematical operator shape."""
    tree = _tree(expression)
    def shape(node):
        if isinstance(node, ast.Expression): return shape(node.body)
        if isinstance(node, ast.Name): return "V"
        if isinstance(node, ast.Constant): return "C"
        if isinstance(node, ast.UnaryOp): return f"{type(node.op).__name__}({shape(node.operand)})"
        if isinstance(node, ast.BinOp): return f"{type(node.op).__name__}({shape(node.left)},{shape(node.right)})"
        raise ValueError("unsupported node")
    return shape(tree)


def evaluate_float(expression: str, variables: dict[str, float]) -> float:
    tree = _tree(expression)
    names = referenced_names(expression)
    if not names.issubset(variables):
        raise ValueError(f"unknown variables: {sorted(names - set(variables))}")
    def ev(node):
        if isinstance(node, ast.Expression): return ev(node.body)
        if isinstance(node, ast.Constant): return float(node.value)
        if isinstance(node, ast.Name): return float(variables[node.id])
        if isinstance(node, ast.UnaryOp): return +ev(node.operand) if isinstance(node.op, ast.UAdd) else -ev(node.operand)
        if isinstance(node, ast.BinOp):
            a, b = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Add): return a + b
            if isinstance(node.op, ast.Sub): return a - b
            if isinstance(node.op, ast.Mult): return a * b
            if isinstance(node.op, ast.Div):
                if abs(b) < 1e-15: raise ZeroDivisionError
                return a / b
            if isinstance(node.op, ast.Pow):
                if abs(b) > 6: raise ValueError("exponent too large")
                return a ** b
        raise ValueError("unsupported expression")
    value = ev(tree)
    if not (-1e12 < value < 1e12): raise ValueError("answer outside supported range")
    return value


def evaluate_decimal(expression: str, variables: dict[str, float]) -> Decimal:
    tree = _tree(expression)
    names = referenced_names(expression)
    if not names.issubset(variables): raise ValueError("unknown variable")
    def ev(node):
        if isinstance(node, ast.Expression): return ev(node.body)
        if isinstance(node, ast.Constant): return Decimal(str(node.value))
        if isinstance(node, ast.Name): return Decimal(str(variables[node.id]))
        if isinstance(node, ast.UnaryOp): return ev(node.operand) if isinstance(node.op, ast.UAdd) else -ev(node.operand)
        if isinstance(node, ast.BinOp):
            a, b = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Add): return a + b
            if isinstance(node.op, ast.Sub): return a - b
            if isinstance(node.op, ast.Mult): return a * b
            if isinstance(node.op, ast.Div):
                if b == 0: raise ZeroDivisionError
                return a / b
            if isinstance(node.op, ast.Pow):
                if b != b.to_integral_value() or abs(int(b)) > 6: raise ValueError("unsupported exponent")
                return a ** int(b)
        raise ValueError("unsupported expression")
    return ev(tree)
