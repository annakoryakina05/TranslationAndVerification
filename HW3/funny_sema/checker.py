"""Семантический анализ Funny: имена, области видимости, типы, вывод типов локальных.

Вход — AST из HW2 (parse_program(text, check_sorts=False)).
Выход — тот же AST с аннотациями (node.ty — тип выражения, node.ref — к чему
относится имя), таблицы символов функций и список диагностик.

Проход по модулю:
  1. собрать сигнатуры всех функций и формул (вызывать можно объявленные ниже);
  2. проверить каждую формулу и функцию:
       - объявить параметры / результаты / локальные в области функции;
       - проверить requires, ensures, тело — у каждой части своя видимость;
       - типы выражений выводятся снизу вверх и сверяются с ожидаемыми через unify;
       - локальным без аннотации даётся переменная типа (TVar), её связывает
         первое использование с однозначным типом (обычно первое присваивание);
  3. в конце функции: невыведенные типы -> ошибка; аннотации записываются в узлы.

Ошибки не останавливают анализ: после ошибки подставляется тип ERR, совместимый
со всем, поэтому одна ошибка не порождает каскад следующих.
"""
import difflib

from funny_parser import ast as A
from funny_parser.tokens import Diagnostic

from .symbols import KIND_NAMES, Scope, Symbol
from .types import (BOOL, ERR, INT, Array, Signature, TVar, binding_origin, from_annotation,
                    resolve, show, unify)

INT_MIN, INT_MAX = -(2 ** 31), 2 ** 31 - 1


def plural(n, one, few, many):
    """plural(2, 'аргумент', 'аргумента', 'аргументов') -> '2 аргумента'."""
    if n % 10 == 1 and n % 100 != 11:
        w = one
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        w = few
    else:
        w = many
    return f"{n} {w}"
VISIBLE = {
    "requires": {"param"},
    "ensures": {"param", "return"},
    "body": {"param", "return", "local"},
    "formula": {"param"},
}
CLAUSE_NAMES = {"requires": "в requires (там видны только параметры)",
                "ensures": "в ensures (там видны параметры и возвращаемые значения)",
                "formula": "в теле формулы (там видны только её параметры)"}


class SemaResult:
    def __init__(self, module, tables, signatures, diags):
        self.module = module
        self.tables = tables            # имя функции/формулы -> [Symbol]
        self.signatures = signatures    # имя -> Signature
        self.diags = diags


class Checker:
    def __init__(self, allow_array_locals=False):
        self.allow_array_locals = allow_array_locals
        self.diags = []
        self.globals = {}
        self.tables = {}
        self.scope = None          # текущая область (функция или квантор)
        self.clause = "body"       # где сейчас стоит выражение
        self.pending = []          # (узел, тип) — типы окончательно известны в конце функции

    # ------------------------------------------------------------------ ошибки
    def error(self, node, message, phase="type"):
        line, col = getattr(node, "line", 0), getattr(node, "col", 0)
        for d in self.diags:
            if (d.line, d.col, d.message) == (line, col, message):
                return
        self.diags.append(Diagnostic(line, col, message, phase))

    @staticmethod
    def suggest(name, candidates):
        close = difflib.get_close_matches(name, sorted(candidates), n=1, cutoff=0.6)
        return f"; возможно, имелось в виду '{close[0]}'" if close else ""

    # ------------------------------------------------------------------ модуль
    def check_module(self, m):
        self.globals = {"length": Signature("length", "builtin", [Array(INT)], [INT])}
        decls = []
        for d in m.decls:
            old = self.globals.get(d.name)
            if old is not None:
                where = "встроенная функция" if old.kind == "builtin" else \
                    f"{KIND_NAMES[old.kind]}, объявлена в {old.line}:{old.col}"
                self.error(d, f"повторное объявление '{d.name}': это имя уже занято ({where}); "
                              "перегрузка функций в Funny не поддерживается", "name")
                continue
            params = [from_annotation(p.type) for p in d.params]
            if isinstance(d, A.Formula):
                sig = Signature(d.name, "formula", params, [], d.line, d.col)
            else:
                sig = Signature(d.name, "function", params,
                                [from_annotation(r.type) for r in d.returns], d.line, d.col)
            self.globals[d.name] = sig
            decls.append(d)
        for d in decls:
            if isinstance(d, A.Formula):
                self.check_formula(d)
            else:
                self.check_function(d)
        return SemaResult(m, self.tables, self.globals, self.diags)

    # ------------------------------------------------------- функции и формулы
    def begin(self, owner):
        self.scope = Scope("function")
        self.pending = []
        self.owner = owner

    def declare_vars(self, defs, kind):
        for v in defs:
            sym = Symbol(v.name, kind, from_annotation(v.type), v.line, v.col, v.type, v)
            old = self.scope.declare(sym)
            if old is not None:
                self.error(v, f"повторное объявление '{v.name}': имя уже занято — "
                              f"{old.describe()}", "name")

    def check_formula(self, f):
        self.begin(f)
        self.declare_vars(f.params, "param")
        self.clause = "formula"
        f.body = self.expect(f.body, True, BOOL, f"тело формулы '{f.name}'")
        self.finish(f)

    def check_function(self, f):
        self.begin(f)
        self.declare_vars(f.params, "param")
        self.declare_vars(f.returns, "return")
        self.declare_vars(f.uses, "local")
        for v in f.uses:
            if v.type == "int[]" and not self.allow_array_locals:
                self.error(v, f"локальная переменная '{v.name}' объявлена как int[], но по "
                              "спецификации Funny локальные переменные могут быть только int")
        if f.requires is not None:
            self.clause = "requires"
            f.requires = self.expect(f.requires, True, BOOL, "предусловие requires")
        if f.ensures is not None:
            self.clause = "ensures"
            f.ensures = self.expect(f.ensures, True, BOOL, "постусловие ensures")
        self.clause = "body"
        self.check_stmt(f.body)
        self.finish(f)

    def finish(self, owner):
        """Конец функции: проверить выведенные типы и записать аннотации в AST."""
        for sym in self.scope.symbols.values():
            if not sym.inferred:
                continue
            t = resolve(sym.type)
            if isinstance(t, TVar):
                self.error(sym.node, f"не удалось вывести тип локальной переменной '{sym.name}': "
                                     "ей ничего не присваивается и она не используется там, где тип "
                                     "однозначен; укажите тип явно (uses x: int)")
                sym.type = ERR
                continue
            origin = binding_origin(sym.type)
            sym.node.type = show(t)
            if origin:
                sym.node.inferred = f"{origin[0]}:{origin[1]}"
            if isinstance(t, Array) and not self.allow_array_locals:
                where = f" (тип выведен в {origin[0]}:{origin[1]})" if origin else ""
                self.error(sym.node, f"локальная переменная '{sym.name}' получила тип int[]{where}, "
                                     "но по спецификации Funny локальные переменные могут быть только int")
        for node, t in self.pending:
            node.ty = show(t)
        self.tables[owner.name] = list(self.scope.symbols.values())

    # ------------------------------------------------------------- переменные
    def lookup_var(self, name, node):
        """Найти переменную с учётом квантора и видимости части функции. None — ошибка уже выдана."""
        sym = self.scope.lookup(name)
        if sym is not None:
            if sym.kind == "bound" or sym.kind in VISIBLE[self.clause]:
                return sym
            self.error(node, f"имя '{name}' ({KIND_NAMES[sym.kind]}, объявлено в {sym.line}:{sym.col}) "
                             f"недоступно {CLAUSE_NAMES[self.clause]}", "name")
            return None
        if name in self.globals:
            g = self.globals[name]
            self.error(node, f"'{name}' — {KIND_NAMES[g.kind]}, а не переменная; "
                             f"вызов записывается как {name}(...)", "name")
            return None
        visible = [n for n, s in self._visible_vars().items()]
        self.error(node, f"неизвестная переменная '{name}'{self.suggest(name, visible)}", "name")
        return None

    def _visible_vars(self):
        out, s = {}, self.scope
        while s is not None:
            for n, sym in s.symbols.items():
                if n not in out and (sym.kind == "bound" or sym.kind in VISIBLE[self.clause]):
                    out[n] = sym
            s = s.parent
        return out

    def writable(self, name, node):
        sym = self.scope.lookup(name)
        if sym is None:
            return self.lookup_var(name, node)       # выдаст «неизвестная переменная»
        if sym.kind == "param":
            self.error(node, f"нельзя присваивать параметру '{name}' ({sym.line}:{sym.col}): "
                             "параметры функции доступны только для чтения", "name")
            return None
        if sym.kind == "bound":
            self.error(node, f"нельзя присваивать переменной квантора '{name}'", "name")
            return None
        return sym

    # --------------------------------------------------------- ожидание типа
    def expect(self, e, pred, expected, what):
        node, t = self.infer(e, pred)
        self.require(node, t, expected, what)
        return node

    def require(self, node, actual, expected, what):
        if unify(actual, expected, (node.line, node.col)):
            return True
        msg = f"{what}: ожидалось {show(expected)}, получено {show(actual)}"
        if isinstance(node, A.Var):
            sym = self.scope.lookup(node.name)
            if sym is not None and sym.inferred:
                o = binding_origin(sym.type)
                if o:
                    msg += f" (тип переменной '{node.name}' выведен как {show(sym.type)} в {o[0]}:{o[1]})"
        self.error(node, msg)
        return False

    # ------------------------------------------------------------- выражения
    def infer(self, e, pred):
        """(новый узел, тип). pred=True — разрешены кванторы и ссылки на формулы."""
        node, t = getattr(self, "e_" + type(e).__name__)(e, pred)
        self.pending.append((node, t))
        return node, t

    def e_IntLit(self, e, pred, negated=False):
        limit = -INT_MIN if negated else INT_MAX
        if e.value > limit:
            self.error(e, f"константа {'-' if negated else ''}{e.value} не помещается в int "
                          f"(32 бита: от {INT_MIN} до {INT_MAX})")
        return e, INT

    def e_BoolLit(self, e, pred):
        return e, BOOL

    def e_Var(self, e, pred):
        sym = self.lookup_var(e.name, e)
        if sym is None:
            return e, ERR
        e.ref = sym.kind
        return e, sym.type

    def e_Index(self, e, pred):
        sym = self.lookup_var(e.array, e)
        if sym is not None:
            e.ref = sym.kind
            if not unify(sym.type, Array(INT), (e.line, e.col)):
                self.error(e, f"'{e.array}' имеет тип {show(sym.type)}, индексировать можно "
                              "только массив int[]")
        e.index = self.expect(e.index, False, INT, f"индекс массива '{e.array}'")
        return e, INT

    def e_Neg(self, e, pred):
        if isinstance(e.operand, A.IntLit):            # -2147483648 допустимо
            node, _ = self.e_IntLit(e.operand, pred, negated=True)
            self.pending.append((node, INT))
        else:
            e.operand = self.expect(e.operand, False, INT, "операнд унарного '-'")
        return e, INT

    def e_Binary(self, e, pred):
        e.left = self.expect(e.left, False, INT, f"левый операнд '{e.op}'")
        e.right = self.expect(e.right, False, INT, f"правый операнд '{e.op}'")
        return e, INT

    def e_Compare(self, e, pred):
        e.left = self.expect(e.left, False, INT, f"левый операнд сравнения '{e.op}'")
        e.right = self.expect(e.right, False, INT, f"правый операнд сравнения '{e.op}'")
        return e, BOOL

    def e_Not(self, e, pred):
        e.operand = self.expect(e.operand, pred, BOOL, "операнд 'not'")
        return e, BOOL

    def e_Logical(self, e, pred):
        e.left = self.expect(e.left, pred, BOOL, f"левый операнд '{e.op}'")
        e.right = self.expect(e.right, pred, BOOL, f"правый операнд '{e.op}'")
        return e, BOOL

    def e_Quantifier(self, e, pred):
        if not pred:
            self.error(e, f"квантор '{e.quant}' допустим только в предикатах (requires, ensures, "
                          "invariant, assert, assume, тело формулы), а не в условии if/while")
        clash = self._visible_vars().get(e.var.name)
        if clash is not None:
            self.error(e.var, f"имя переменной квантора '{e.var.name}' уже используется в этой "
                              f"области: {clash.describe()}", "name")
        outer = self.scope
        self.scope = Scope("quantifier", outer)
        sym = Symbol(e.var.name, "bound", from_annotation(e.var.type), e.var.line, e.var.col,
                     e.var.type, e.var)
        self.scope.declare(sym)
        try:
            e.body = self.expect(e.body, True, BOOL, f"тело квантора '{e.quant}'")
        finally:
            self.scope = outer
        return e, BOOL

    def e_Call(self, e, pred):
        sig = self.globals.get(e.name)
        if sig is None:
            fns = [n for n, s in self.globals.items() if s.kind != "formula" or pred]
            self.error(e, f"неизвестная функция '{e.name}'{self.suggest(e.name, fns)}", "name")
            for i, a in enumerate(e.args):
                e.args[i], _ = self.infer(a, False)
            return e, ERR
        if sig.kind == "formula":
            if pred:
                ref = A.FormulaRef(e.name, e.args, line=e.line, col=e.col)
                return self.e_FormulaRef(ref, pred)
            self.error(e, f"'{e.name}' — формула ({sig.line}:{sig.col}); ссылки на формулы "
                          "допустимы только в предикатах, а не в выражениях и условиях if/while", "name")
            self.check_args(e, sig)
            return e, ERR
        e.ref = sig.kind
        self.check_args(e, sig)
        if len(sig.returns) != 1:
            self.error(e, f"функция '{e.name}' возвращает {plural(len(sig.returns), 'значение', 'значения', 'значений')} и не может "
                          "использоваться в выражении; используйте кортежное присваивание "
                          f"({', '.join('x' + str(i + 1) for i in range(len(sig.returns)))} = {e.name}(...);)")
            return e, ERR
        return e, sig.returns[0]

    def e_FormulaRef(self, e, pred):
        sig = self.globals.get(e.name)
        if sig is None:
            self.error(e, f"неизвестная формула '{e.name}'", "name")
            return e, ERR
        if sig.kind != "formula":
            self.error(e, f"'{e.name}' — {KIND_NAMES[sig.kind]}, а не формула", "name")
            return e, ERR
        if not pred:
            self.error(e, f"ссылка на формулу '{e.name}' допустима только в предикатах", "name")
        e.ref = "formula"
        self.check_args(e, sig)
        return e, BOOL

    def check_args(self, e, sig):
        what = {"function": "функции", "builtin": "встроенной функции", "formula": "формулы"}[sig.kind]
        if len(e.args) != len(sig.params):
            self.error(e, f"{what} '{e.name}' нужно {plural(len(sig.params), 'аргумент', 'аргумента', 'аргументов')} "
                          f"(сигнатура {sig}), передано {len(e.args)}")
        for i, a in enumerate(e.args):
            if i < len(sig.params):
                e.args[i] = self.expect(a, False, sig.params[i],
                                        f"аргумент {i + 1} {what} '{e.name}'")
            else:
                e.args[i], _ = self.infer(a, False)

    # -------------------------------------------------------------- операторы
    def check_stmt(self, s):
        getattr(self, "s_" + type(s).__name__)(s)

    def s_Block(self, s):
        for st in s.stmts:
            self.check_stmt(st)

    def s_If(self, s):
        s.cond = self.expect(s.cond, False, BOOL, "условие if")
        self.check_stmt(s.then)
        if s.otherwise is not None:
            self.check_stmt(s.otherwise)

    def s_While(self, s):
        s.cond = self.expect(s.cond, False, BOOL, "условие while")
        if s.invariant is not None:
            s.invariant = self.expect(s.invariant, True, BOOL, "инвариант цикла")
        self.check_stmt(s.body)

    def s_Assert(self, s):
        s.pred = self.expect(s.pred, True, BOOL, "assert")

    def s_Assume(self, s):
        s.pred = self.expect(s.pred, True, BOOL, "assume")

    def s_Assign(self, s):
        if len(s.targets) > 1:
            return self.tuple_assign(s)
        name, v = s.targets[0], s.value
        sym = self.writable(name, s)
        if isinstance(v, A.ArrayStore):                         # a[i] = e  (сахар: a = store(a, i, e))
            if sym is not None:
                v.ref = sym.kind
                if not unify(sym.type, Array(INT), (s.line, s.col)):
                    self.error(s, f"присваивание элементу: '{name}' имеет тип {show(sym.type)}, "
                                  "а элементы есть только у массива int[]")
            v.index = self.expect(v.index, False, INT, f"индекс массива '{name}'")
            v.value = self.expect(v.value, False, INT, f"значение элемента массива '{name}'")
            self.pending.append((v, Array(INT)))
            return
        node, t = self.infer(v, False)
        s.value = node
        if sym is not None:
            if not unify(sym.type, t, (s.line, s.col)):
                msg = f"присваивание '{name}': переменная имеет тип {show(sym.type)}, " \
                      f"а значение — {show(t)}"
                if sym.inferred and binding_origin(sym.type):
                    o = binding_origin(sym.type)
                    msg += f" (тип '{name}' выведен в {o[0]}:{o[1]})"
                self.error(s, msg)

    def tuple_assign(self, s):
        seen = {}
        syms = []
        for name in s.targets:
            if name in seen:
                self.error(s, f"переменная '{name}' встречается в кортежном присваивании дважды", "name")
            seen[name] = True
            syms.append(self.writable(name, s))
        call = s.value
        if not isinstance(call, A.Call):            # парсер уже сообщил об ошибке
            self.infer(call, False)
            return
        sig = self.globals.get(call.name)
        if sig is None or sig.kind == "formula":
            s.value, _ = self.infer(call, False)    # сообщит «неизвестная функция» / «это формула»
            return
        call.ref = sig.kind
        self.check_args(call, sig)
        if len(sig.returns) != len(s.targets):
            self.error(s, f"функция '{call.name}' возвращает {plural(len(sig.returns), 'значение', 'значения', 'значений')}, "
                          f"а слева {plural(len(s.targets), 'переменная', 'переменные', 'переменных')}")
        for i, (name, sym) in enumerate(zip(s.targets, syms)):
            if sym is None or i >= len(sig.returns):
                continue
            if not unify(sym.type, sig.returns[i], (s.line, s.col)):
                self.error(s, f"кортежное присваивание: '{name}' имеет тип {show(sym.type)}, "
                              f"а {i + 1}-й результат '{call.name}' — {show(sig.returns[i])}")
        call.ty = "(" + ", ".join(show(r) for r in sig.returns) + ")"


def analyze(module, allow_array_locals=False):
    checker = Checker(allow_array_locals)
    res = checker.check_module(module)
    res.diags.sort(key=lambda d: (d.line, d.col))
    return res
