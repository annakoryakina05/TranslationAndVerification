import sys

from . import ast as A
from .sortcheck import check_module, check_expr
from .tokens import Diagnostic, tokenize

MAX_ERRORS = 100
RELOPS = {"EQ": "==", "NE": "!=", "LT": "<", "LE": "<=", "GT": ">", "GE": ">="}
STMT_START = {"LBRACE", "KW_IF", "KW_WHILE", "KW_ASSERT", "KW_ASSUME", "IDENT"}
STMT_SYNC = {"LBRACE", "KW_IF", "KW_WHILE", "KW_ASSERT", "KW_ASSUME"}

NAMES = {
    "IDENT": "идентификатор", "INT": "число", "EOF": "конец файла",
    "LPAREN": "'('", "RPAREN": "')'", "LBRACKET": "'['", "RBRACKET": "']'",
    "LBRACE": "'{'", "RBRACE": "'}'", "COMMA": "','", "SEMI": "';'", "COLON": "':'",
    "BAR": "'|'", "ASSIGN": "'='", "FAT_ARROW": "'=>'", "ARROW": "'->'",
}


def name_of(kind):
    if kind in NAMES:
        return NAMES[kind]
    if kind.startswith("KW_"):
        return f"'{kind[3:].lower()}'"
    return kind


def found(tok):
    if tok.kind == "EOF":
        return "конец файла"
    if tok.kind == "IDENT":
        return f"идентификатор '{tok.lexeme}'"
    if tok.kind == "INT":
        return f"число '{tok.lexeme}'"
    return f"'{tok.lexeme}'"


class ParseError(Exception):
    pass


class TooManyErrors(Exception):
    pass


class InternalLoopError(RuntimeError):
    """Срабатывает, если парсер перестал продвигаться (защита от зацикливания)."""


class Parser:
    def __init__(self, tokens, diags):
        self.toks = tokens
        self.i = 0
        self.diags = diags
        self.steps = 0
        self.step_limit = 50 * len(tokens) + 1000

    # ------------------------------------------------------------ утилиты
    @property
    def tok(self):
        return self.toks[self.i]

    def peek(self, k=1):
        return self.toks[min(self.i + k, len(self.toks) - 1)]

    def at(self, *kinds):
        return self.tok.kind in kinds

    def advance(self):
        t = self.tok
        if t.kind != "EOF":
            self.i += 1
        return t

    def accept(self, kind):
        return self.advance() if self.at(kind) else None

    def tick(self):
        self.steps += 1
        if self.steps > self.step_limit:
            raise InternalLoopError("парсер не продвигается")

    def report(self, tok, message, phase="syntax"):
        last = self.diags[-1] if self.diags else None
        if last and (last.line, last.col) == (tok.line, tok.col) and last.phase == phase:
            return                                   # не дублируем ошибку в той же точке
        self.diags.append(Diagnostic(tok.line, tok.col, message, phase))
        if sum(d.phase != "lexical" for d in self.diags) >= MAX_ERRORS:
            raise TooManyErrors()

    def fail(self, message, tok=None):
        self.report(tok or self.tok, message)
        raise ParseError(message)

    def expect(self, kind, context=""):
        if self.at(kind):
            return self.advance()
        ctx = f" {context}" if context else ""
        self.fail(f"ожидалось {name_of(kind)}{ctx}, найдено {found(self.tok)}")

    @staticmethod
    def pos(tok):
        return {"line": tok.line, "col": tok.col}

    # -------------------------------------------------------------- модуль
    # module -> decl decl_list
    def parse_module(self):
        start = self.tok
        decls = []
        if self.at("EOF"):
            self.report(start, "пустой ввод: ожидалось объявление функции или формулы")
        while not self.at("EOF"):
            self.tick()
            begin = self.i
            try:
                decls.append(self.parse_decl())
            except ParseError:
                self.sync_decl(begin)
        return A.Module(decls, line=start.line, col=start.col)

    def sync_decl(self, begin):
        """Пропуск до начала следующего объявления: 'function' или идентификатор
        с '(' на нулевой глубине скобок, стоящий в начале строки или сразу после '}' / ';'."""
        if self.i == begin:
            self.advance()
        depth = 0
        while not self.at("EOF"):
            self.tick()
            t, prev = self.tok, self.toks[self.i - 1]
            if depth == 0 and t.kind == "KW_FUNCTION":
                return
            if (depth == 0 and t.kind == "IDENT" and self.peek().kind == "LPAREN"
                    and (prev.kind in ("RBRACE", "SEMI") or prev.line < t.line)):
                return
            if t.kind == "LBRACE":
                depth += 1
            elif t.kind == "RBRACE":
                depth = max(0, depth - 1)
            self.advance()

    # decl -> IDENT ( params ) decl_tail | KW_FUNCTION IDENT ( params ) fn_tail
    def parse_decl(self):
        first = self.tok
        if self.at("KW_FUNCTION"):
            self.advance()
            name = self.expect("IDENT", "(имя функции)")
            params = self.parse_params()
            return self.parse_fn_tail(first, name.lexeme, params, allow_formula=False)
        if not self.at("IDENT"):
            self.fail(f"ожидалось объявление функции или формулы, найдено {found(self.tok)}")
        name = self.advance()
        params = self.parse_params()
        if self.at("FAT_ARROW"):                      # decl_tail -> FAT_ARROW expr
            self.advance()
            body = self.parse_expr()
            return A.Formula(name.lexeme, params, body, line=first.line, col=first.col)
        return self.parse_fn_tail(first, name.lexeme, params, allow_formula=True)

    # fn_tail -> requires_opt KW_RETURNS var_def var_def_rest ensures_opt uses_opt statement
    def parse_fn_tail(self, first, name, params, allow_formula):
        requires = None
        if self.accept("KW_REQUIRES"):
            requires = self.parse_expr()
        if not self.at("KW_RETURNS"):
            opts = "'requires', 'returns' или '=>'" if allow_formula and requires is None else "'returns'"
            self.fail(f"ожидалось {opts}, найдено {found(self.tok)}")
        self.advance()
        returns = self.parse_var_defs()
        ensures = self.parse_expr() if self.accept("KW_ENSURES") else None
        uses = self.parse_local_defs() if self.accept("KW_USES") else []
        if not self.at(*STMT_START):
            self.fail(f"ожидалось тело функции (оператор или блок), найдено {found(self.tok)}")
        body = self.parse_statement()
        return A.Function(name, params, requires, returns, ensures, uses, body,
                          line=first.line, col=first.col)

    # LPAREN param_list RPAREN
    def parse_params(self):
        self.expect("LPAREN", "(начало списка параметров)")
        params = []
        if not self.at("RPAREN"):
            params = self.parse_var_defs()
        self.expect("RPAREN", "(конец списка параметров)")
        return params

    # var_def var_def_rest
    def parse_var_defs(self):
        defs = [self.parse_var_def()]
        while self.accept("COMMA"):
            defs.append(self.parse_var_def())
        return defs

    # var_def -> IDENT COLON type
    def parse_var_def(self):
        name = self.expect("IDENT", "(имя переменной)")
        self.expect("COLON", "(после имени переменной)")
        return A.VarDef(name.lexeme, self.parse_type(), line=name.line, col=name.col)

    # type -> KW_INT array_opt ; array_opt -> LBRACKET RBRACKET | ε
    def parse_type(self):
        self.expect("KW_INT", "(тип: int или int[])")
        if self.accept("LBRACKET"):
            self.expect("RBRACKET", "(тип int[])")
            return "int[]"
        return "int"

    # (HW3) uses: local_def local_def_rest ; local_def -> IDENT type_opt ; type_opt -> COLON type | ε
    # Тип локальной переменной можно не писать — его выведет семантический анализ (funny_sema).
    def parse_local_defs(self):
        defs = [self.parse_local_def()]
        while self.accept("COMMA"):
            defs.append(self.parse_local_def())
        return defs

    def parse_local_def(self):
        name = self.expect("IDENT", "(имя локальной переменной)")
        typ = self.parse_type() if self.accept("COLON") else None
        return A.VarDef(name.lexeme, typ, line=name.line, col=name.col)

    # ------------------------------------------------------------ операторы
    def parse_statement(self):
        k = self.tok.kind
        if k == "LBRACE":
            return self.parse_block()
        if k == "KW_IF":
            return self.parse_if()
        if k == "KW_WHILE":
            return self.parse_while()
        if k in ("KW_ASSERT", "KW_ASSUME"):
            return self.parse_assert()
        if k == "IDENT":
            return self.parse_assign()
        hint = " ('else' без 'if')" if k == "KW_ELSE" else ""
        self.fail(f"ожидался оператор (присваивание, if, while, assert, assume или блок), "
                  f"найдено {found(self.tok)}{hint}")

    # block -> LBRACE stmt_list RBRACE
    def parse_block(self):
        lb = self.expect("LBRACE")
        stmts = []
        while not self.at("RBRACE", "EOF"):
            self.tick()
            begin = self.i
            try:
                stmts.append(self.parse_statement())
            except ParseError:
                self.sync_stmt(begin)
        if self.at("EOF"):
            self.fail(f"ожидалось '}}' для блока, открытого в {lb.line}:{lb.col}, найдено конец файла")
        self.advance()
        return A.Block(stmts, line=lb.line, col=lb.col)

    def sync_stmt(self, begin):
        """Режим паники внутри блока."""
        if self.i == begin and not self.at("RBRACE", "EOF"):
            self.advance()
        while not self.at("EOF"):
            self.tick()
            if self.at("SEMI"):
                self.advance()
                return
            if self.at("RBRACE") or self.at(*STMT_SYNC):
                return
            self.advance()

    # if_stmt -> KW_IF LPAREN expr RPAREN statement else_opt
    def parse_if(self):
        kw = self.advance()
        cond = self.parse_paren_cond("if")
        then = self.parse_statement()
        otherwise = None
        if self.accept("KW_ELSE"):           # висячий else -> к ближайшему if
            otherwise = self.parse_statement()
        return A.If(cond, then, otherwise, line=kw.line, col=kw.col)

    # while_stmt -> KW_WHILE LPAREN expr RPAREN invariant_opt statement
    def parse_while(self):
        kw = self.advance()
        cond = self.parse_paren_cond("while")
        inv = self.parse_expr() if self.accept("KW_INVARIANT") else None
        body = self.parse_statement()
        return A.While(cond, inv, body, line=kw.line, col=kw.col)

    def parse_paren_cond(self, what):
        lp = self.expect("LPAREN", f"после '{what}'")
        cond = self.parse_expr()
        if not self.at("RPAREN"):
            self.fail(f"ожидалось ')' для '(' из {lp.line}:{lp.col}, найдено {found(self.tok)}")
        self.advance()
        return cond

    # assert_stmt / assume_stmt -> KW_ASSERT expr SEMI
    def parse_assert(self):
        kw = self.advance()
        pred = self.parse_expr()
        self.expect("SEMI", f"в конце '{kw.lexeme}'")
        cls = A.Assert if kw.kind == "KW_ASSERT" else A.Assume
        return cls(pred, line=kw.line, col=kw.col)

    # assign -> IDENT assign_rest
    def parse_assign(self):
        name = self.advance()
        if self.accept("ASSIGN"):                                   # x = e;
            value = self.parse_expr()
            self.expect("SEMI", "в конце присваивания")
            return A.Assign([name.lexeme], value, line=name.line, col=name.col)
        if self.at("LBRACKET"):                                     # x[i] = e;
            lb = self.advance()
            index = self.parse_expr()
            self.expect("RBRACKET", f"для '[' из {lb.line}:{lb.col}")
            self.expect("ASSIGN", "(присваивание элементу массива)")
            value = self.parse_expr()
            self.expect("SEMI", "в конце присваивания")
            store = A.ArrayStore(name.lexeme, index, value, line=name.line, col=name.col)
            return A.Assign([name.lexeme], store, line=name.line, col=name.col)
        if self.at("COMMA"):                                        # x, y = f(...);
            names = [name.lexeme]
            while self.accept("COMMA"):
                names.append(self.expect("IDENT", "(имя переменной в кортежном присваивании)").lexeme)
            self.expect("ASSIGN", "(кортежное присваивание)")
            value = self.parse_expr()
            if not isinstance(value, A.Call):
                self.report(_tok_at(value),
                            "в кортежном присваивании справа должен быть вызов функции")
            self.expect("SEMI", "в конце присваивания")
            return A.Assign(names, value, line=name.line, col=name.col)
        self.fail(f"ожидалось '=', '[' или ',' после '{name.lexeme}', найдено {found(self.tok)}")

    # ------------------------------------------------------------ выражения
    # expr -> or_expr impl_rest ; impl_rest -> ARROW expr | ε   (правая ассоциативность)
    def parse_expr(self):
        left = self.parse_or()
        if self.at("ARROW"):
            self.advance()
            right = self.parse_expr()
            return A.Logical("->", left, right, line=left.line, col=left.col)
        return left

    def parse_or(self):
        left = self.parse_and()
        while self.at("KW_OR"):
            self.advance()
            right = self.parse_and()
            left = A.Logical("or", left, right, line=left.line, col=left.col)
        return left

    def parse_and(self):
        left = self.parse_not()
        while self.at("KW_AND"):
            self.advance()
            right = self.parse_not()
            left = A.Logical("and", left, right, line=left.line, col=left.col)
        return left

    # not_expr -> KW_NOT not_expr | cmp_expr
    def parse_not(self):
        if self.at("KW_NOT"):
            kw = self.advance()
            return A.Not(self.parse_not(), line=kw.line, col=kw.col)
        return self.parse_cmp()

    # cmp_expr -> add_expr cmp_rest ; cmp_rest -> relop add_expr | ε
    def parse_cmp(self):
        left = self.parse_add()
        if self.tok.kind in RELOPS:
            op = self.advance()
            right = self.parse_add()
            node = A.Compare(RELOPS[op.kind], left, right, line=left.line, col=left.col)
            if self.tok.kind in RELOPS:
                self.fail(f"сравнения нельзя записывать цепочкой: лишний '{self.tok.lexeme}' "
                          f"(используйте 'and')")
            return node
        return left

    def parse_add(self):
        left = self.parse_mul()
        while self.at("PLUS", "MINUS"):
            op = self.advance()
            right = self.parse_mul()
            left = A.Binary(op.lexeme, left, right, line=left.line, col=left.col)
        return left

    def parse_mul(self):
        left = self.parse_unary()
        while self.at("STAR", "SLASH"):
            op = self.advance()
            right = self.parse_unary()
            left = A.Binary(op.lexeme, left, right, line=left.line, col=left.col)
        return left

    # unary -> MINUS unary | primary
    def parse_unary(self):
        if self.at("MINUS"):
            m = self.advance()
            return A.Neg(self.parse_unary(), line=m.line, col=m.col)
        return self.parse_primary()

    def parse_primary(self):
        t = self.tok
        k = t.kind
        if k == "INT":
            self.advance()
            return A.IntLit(int(t.lexeme), line=t.line, col=t.col)
        if k in ("KW_TRUE", "KW_FALSE"):
            self.advance()
            return A.BoolLit(k == "KW_TRUE", line=t.line, col=t.col)
        if k == "IDENT":
            self.advance()
            if self.at("LPAREN"):                              # вызов f(...)
                return A.Call(t.lexeme, self.parse_args(), line=t.line, col=t.col)
            if self.at("LBRACKET"):                            # a[i]
                lb = self.advance()
                index = self.parse_expr()
                self.expect("RBRACKET", f"для '[' из {lb.line}:{lb.col}")
                return A.Index(t.lexeme, index, line=t.line, col=t.col)
            return A.Var(t.lexeme, line=t.line, col=t.col)
        if k == "KW_LENGTH":                                   # length(a)
            self.advance()
            return A.Call("length", self.parse_args(), line=t.line, col=t.col)
        if k in ("KW_FORALL", "KW_EXISTS"):
            self.advance()
            lp = self.expect("LPAREN", f"после '{t.lexeme}'")
            var = self.parse_var_def()
            self.expect("BAR", "(разделитель квантора)")
            body = self.parse_expr()
            if not self.at("RPAREN"):
                self.fail(f"ожидалось ')' для '(' из {lp.line}:{lp.col}, найдено {found(self.tok)}")
            self.advance()
            return A.Quantifier(t.lexeme, var, body, line=t.line, col=t.col)
        if k == "LPAREN":
            self.advance()
            e = self.parse_expr()
            if not self.at("RPAREN"):
                self.fail(f"ожидалось ')' для '(' из {t.line}:{t.col}, найдено {found(self.tok)}")
            self.advance()
            return e
        self.fail(f"ожидалось выражение, найдено {found(t)}")

    # LPAREN args RPAREN ; args -> expr args_rest | ε
    def parse_args(self):
        lp = self.expect("LPAREN")
        args = []
        if not self.at("RPAREN"):
            args.append(self.parse_expr())
            while self.accept("COMMA"):
                args.append(self.parse_expr())
        if not self.at("RPAREN"):
            self.fail(f"ожидалось ')' или ',' в списке аргументов (открыт в {lp.line}:{lp.col}), "
                      f"найдено {found(self.tok)}")
        self.advance()
        return args


class _Pos:
    def __init__(self, line, col):
        self.line, self.col = line, col


def _tok_at(node):
    return _Pos(node.line, node.col)


# ------------------------------------------------------------------- API
def _finish(diags):
    diags.sort(key=lambda d: (d.line, d.col))
    return diags


def parse_program(text, check_sorts=True):
    """Разбор программы. Возвращает (Module, [Diagnostic]). При ошибках Module частичный.

    check_sorts=False отключает проверку видов выражений (sortcheck.py): её целиком
    берёт на себя семантический анализ HW3 (funny_sema), который знает типы и имена."""
    diags = []
    toks = tokenize(text, diags)
    p = Parser(toks, diags)
    module = A.Module([], line=1, col=1)
    old_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(max(old_limit, 20000))
    try:
        module = p.parse_module()
    except TooManyErrors:
        t = p.tok
        diags.append(Diagnostic(t.line, t.col, f"слишком много ошибок (> {MAX_ERRORS}), разбор остановлен"))
    except RecursionError:
        t = p.tok
        diags.append(Diagnostic(t.line, t.col, "слишком глубокая вложенность выражений"))
    finally:
        sys.setrecursionlimit(old_limit)
    if check_sorts:
        check_module(module, diags)
    return module, _finish(diags)


def parse_expression(text, mode="expr"):
    """Разбор отдельного выражения (для тестов). mode: expr | cond | pred."""
    diags = []
    toks = tokenize(text, diags)
    p = Parser(toks, diags)
    node = None
    try:
        node = p.parse_expr()
        if not p.at("EOF"):
            p.fail(f"лишний токен после выражения: {found(p.tok)}")
    except (ParseError, TooManyErrors):
        node = None
    if node is not None:
        node = check_expr(node, mode, diags)
    return node, _finish(diags)
