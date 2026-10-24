# AST языка Funny: API и формат

Узлы описаны в [`funny_parser/ast.py`](funny_parser/ast.py) (Python `dataclass`).
У **каждого** узла есть `line` и `col` — позиция его первого токена (с 1).

## API

```python
from funny_parser import parse_program, parse_expression, to_text, to_json

module, diagnostics = parse_program(source_text)   # Module + список Diagnostic
if diagnostics:
    for d in diagnostics:                           # d.line, d.col, d.message, d.phase
        print(d)                                    # "3:7: ожидалось ';' ..."
else:
    print(to_text(module))                          # текстовое дерево
    print(to_json(module))                          # JSON

node, diags = parse_expression("a + b * c", mode="expr")   # mode: expr | cond | pred
```

`phase` у диагностики: `lexical` (лексер), `syntax` (парсер), `sort` (проверка видов выражений).
При ошибках `Module` частичный: в нём только то, что удалось разобрать.

## Узлы

**Объявления**

| Узел | Поля |
|---|---|
| `Module` | `decls`: список `Function` / `Formula` |
| `Function` | `name`, `params: [VarDef]`, `requires: expr \| null`, `returns: [VarDef]`, `ensures: expr \| null`, `uses: [VarDef]`, `body: statement` |
| `Formula` | `name`, `params: [VarDef]`, `body: expr` |
| `VarDef` | `name`, `type`: `"int"` или `"int[]"` |

**Операторы**

| Узел | Поля | Источник |
|---|---|---|
| `Block` | `stmts` | `{ ... }` |
| `Assign` | `targets: [str]`, `value` | `x = e;`, `x, y = f(...);` |
| `Assign` + `ArrayStore` | `targets: [a]`, `value: ArrayStore(a, i, e)` | `a[i] = e;` (сахар) |
| `If` | `cond`, `then`, `otherwise: statement \| null` | `if (...) ... else ...` |
| `While` | `cond`, `invariant: expr \| null`, `body` | `while (...) invariant ... ...` |
| `Assert` / `Assume` | `pred` | `assert P;` / `assume P;` |

**Выражения**

| Узел | Поля | Пример | S-выражение |
|---|---|---|---|
| `IntLit` | `value: int` | `42` | `42` |
| `BoolLit` | `value: bool` | `true` | `true` |
| `Var` | `name` | `x` | `x` |
| `Index` | `array: str`, `index` | `a[i]` | `(index a i)` |
| `ArrayStore` | `array: str`, `index`, `value` | `a[i] = v` | `(store a i v)` |
| `Call` | `name`, `args` | `f(x)`, `length(a)` | `(call f x)` |
| `FormulaRef` | `name`, `args` | `p(x)` в предикате | `(formula p x)` |
| `Neg` | `operand` | `-x` | `(neg x)` |
| `Binary` | `op`: `+ - * /`, `left`, `right` | `a + b` | `(+ a b)` |
| `Compare` | `op`: `== != < <= > >=`, `left`, `right` | `a < b` | `(< a b)` |
| `Not` | `operand` | `not p` | `(not p)` |
| `Logical` | `op`: `and`, `or`, `->`; `left`, `right` | `p and q` | `(and p q)` |
| `Quantifier` | `quant`: `forall`/`exists`, `var: VarDef`, `body` | `forall(i: int \| P)` | `(forall (i int) P)` |

Скобки отдельного узла не дают: структура дерева уже отражает группировку.

**Сахар обновления массива.** `a[i] = e;` превращается в `Assign(targets=["a"],
value=ArrayStore("a", i, e))`, то есть «`a` := копия `a`, где элемент `i` заменён на `e`».
Так следующим этапам (верификация, кодогенерация) не нужен отдельный вид присваивания.

## JSON

Каждый узел — объект `{"node": "<Класс>", "line": L, "col": C, ...поля}`; списки — массивы,
отсутствующее — `null`. Пример для `r = a[i] + 1;`:

```json
{
  "node": "Assign", "line": 5, "col": 3,
  "targets": ["r"],
  "value": {
    "node": "Binary", "line": 5, "col": 7, "op": "+",
    "left":  {"node": "Index", "line": 5, "col": 7, "array": "a",
              "index": {"node": "Var", "line": 5, "col": 9, "name": "i"}},
    "right": {"node": "IntLit", "line": 5, "col": 14, "value": 1}
  }
}
```

## Текстовое дерево

Операторы — деревом с отступами и позициями `@строка:столбец`, выражения — S-выражениями:

```
Module
  Function gcd  @2:1
    params:   x: int, y: int
    requires: (and (> x 0) (> y 0))
    returns:  r: int
    ensures:  (> r 0)
    uses:     a: int, b: int
    body:
      Block  @7:1
        Assign a = x  @8:3
        While (!= a b)  @10:3
          invariant: (and (> a 0) (> b 0))
          body:
            ...
```

Этот формат — эталоны snapshot-тестов (`tests/parser/positive/*.ast`).

## Аннотации семантического анализа (HW3)

После `funny_sema` в узлах заполнены поля, которые парсер оставляет пустыми:

| Поле | У каких узлов | Значение |
|---|---|---|
| `ty` (в JSON — `"type"`) | у **каждого** выражения | `"int"`, `"bool"`, `"int[]"`; у вызова в кортежном присваивании — `"(int, int)"` |
| `ref` | `Var`, `Index`, `Call`, `FormulaRef`, `ArrayStore` | к чему относится имя: `param`, `return`, `local`, `bound` (переменная квантора), `function`, `builtin`, `formula` |
| `VarDef.type` | локальные без аннотации | выведенный тип |
| `VarDef.inferred` | локальные без аннотации | `"строка:столбец"`, где тип был выведен |

Кроме того, `Call` в логической позиции предиката, если имя — формула, заменяется
на `FormulaRef`.

Формат JSON всего результата (`python3 -m funny_sema check FILE --json`):

```json
{
  "format": "funny-typed-ast/1",
  "module": { ...дерево, у выражений есть "type", у имён — "ref"... },
  "symbols": { "gcd": [ {"name": "x", "kind": "param", "type": "int", "line": 2, "col": 5, "inferred": false}, ... ] },
  "signatures": { "gcd": {"kind": "function", "signature": "(int, int) -> (int)"}, ... },
  "diagnostics": [ {"line": 3, "col": 7, "phase": "type", "message": "..."} ]
}
```

Пример узла `r = a[i] + 1;` после анализа:

```json
{"node": "Binary", "line": 5, "col": 7, "op": "+", "type": "int",
 "left":  {"node": "Index", "line": 5, "col": 7, "array": "a", "ref": "param", "type": "int",
           "index": {"node": "Var", "line": 5, "col": 9, "name": "i", "ref": "local", "type": "int"}},
 "right": {"node": "IntLit", "line": 5, "col": 14, "value": 1, "type": "int"}}
```

Текстовый формат (`check` без `--json`) — дерево с таблицей символов каждой функции
и выражениями в виде S-выражений с типами: `(+ (index a i:int):int 1):int`.
