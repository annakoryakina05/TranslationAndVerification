"""Проверка видов выражений после разбора.

Парсер использует ЕДИНУЮ грамматику для expr / condition / predicate
(иначе грамматика не LL(1): по '(' нельзя понять, начинается ли
'(a + b) > c' или '(a > b) and c'). Ограничения спецификации проверяются здесь,
и в итоге принимается ровно язык из docs/funny.md:

  * expr (целое):     числа, переменные, a[i], вызовы, - + * /
  * condition (if/while):  true/false, сравнения, not/and/or/->
  * predicate (requires/ensures/invariant/assert/assume/формула):
                      condition + кванторы + ссылки на формулы.

Вызов f(...) в логической позиции предиката превращается в FormulaRef.
"""
from . import ast as A
from .tokens import Diagnostic

KIND_NAMES = {
    A.BoolLit: "логическая константа", A.Compare: "сравнение", A.Not: "отрицание",
    A.Logical: "логическое выражение", A.Quantifier: "квантор", A.FormulaRef: "ссылка на формулу",
    A.IntLit: "число", A.Var: "переменная", A.Index: "элемент массива", A.Call: "вызов функции",
    A.Neg: "арифметическое выражение", A.Binary: "арифметическое выражение",
}
WHERE = {"cond": "в условии if/while", "pred": "в предикате", "expr": "в выражении"}


def _err(diags, node, msg):
    diags.append(Diagnostic(node.line, node.col, msg, "sort"))


def check_int(e, diags):
    """Целочисленное выражение. Возвращает (возможно изменённый) узел."""
    if isinstance(e, (A.IntLit, A.Var)):
        return e
    if isinstance(e, A.Index):
        e.index = check_int(e.index, diags)
        return e
    if isinstance(e, A.Call):
        e.args = [check_int(a, diags) for a in e.args]
        return e
    if isinstance(e, A.Neg):
        e.operand = check_int(e.operand, diags)
        return e
    if isinstance(e, A.Binary):
        e.left, e.right = check_int(e.left, diags), check_int(e.right, diags)
        return e
    _err(diags, e, f"ожидалось целочисленное выражение, найдено: {KIND_NAMES.get(type(e), '?')}")
    return e


def check_bool(e, pred, diags):
    """Логическое выражение; pred=True разрешает кванторы и ссылки на формулы."""
    if isinstance(e, A.BoolLit):
        return e
    if isinstance(e, A.Compare):
        e.left, e.right = check_int(e.left, diags), check_int(e.right, diags)
        return e
    if isinstance(e, A.Not):
        e.operand = check_bool(e.operand, pred, diags)
        return e
    if isinstance(e, A.Logical):
        e.left, e.right = check_bool(e.left, pred, diags), check_bool(e.right, pred, diags)
        return e
    if isinstance(e, A.Quantifier):
        if not pred:
            _err(diags, e, f"квантор '{e.quant}' допустим только в предикатах "
                           "(requires/ensures/invariant/assert/assume/формула), не в условии")
        e.body = check_bool(e.body, True, diags)
        return e
    if isinstance(e, A.Call):
        if not pred:
            _err(diags, e, f"'{e.name}(...)' в условии: ссылки на формулы допустимы только в предикатах, "
                           "а вызов функции не является условием")
            return e
        ref = A.FormulaRef(e.name, [check_int(a, diags) for a in e.args], line=e.line, col=e.col)
        return ref
    _err(diags, e, f"ожидалось логическое выражение (сравнение, true/false, not/and/or), "
                   f"найдено: {KIND_NAMES.get(type(e), '?')}")
    return e


def check_expr(e, mode, diags):
    if mode == "expr":
        return check_int(e, diags)
    return check_bool(e, mode == "pred", diags)


def check_stmt(s, diags):
    if isinstance(s, A.Block):
        for st in s.stmts:
            check_stmt(st, diags)
    elif isinstance(s, A.Assign):
        v = s.value
        if isinstance(v, A.ArrayStore):
            v.index, v.value = check_int(v.index, diags), check_int(v.value, diags)
        else:
            s.value = check_int(v, diags)
    elif isinstance(s, A.If):
        s.cond = check_bool(s.cond, False, diags)
        check_stmt(s.then, diags)
        if s.otherwise is not None:
            check_stmt(s.otherwise, diags)
    elif isinstance(s, A.While):
        s.cond = check_bool(s.cond, False, diags)
        if s.invariant is not None:
            s.invariant = check_bool(s.invariant, True, diags)
        check_stmt(s.body, diags)
    elif isinstance(s, (A.Assert, A.Assume)):
        s.pred = check_bool(s.pred, True, diags)


def check_module(m, diags):
    for d in m.decls:
        if isinstance(d, A.Formula):
            d.body = check_bool(d.body, True, diags)
        elif isinstance(d, A.Function):
            if d.requires is not None:
                d.requires = check_bool(d.requires, True, diags)
            if d.ensures is not None:
                d.ensures = check_bool(d.ensures, True, diags)
            check_stmt(d.body, diags)
