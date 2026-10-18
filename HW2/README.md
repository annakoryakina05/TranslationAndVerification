# HW2. Парсер Funny: LL(1), рекурсивный спуск + лексер из HW1

Python ≥ 3.10, только стандартная библиотека — ничего устанавливать не нужно.

* **Ветка:** LL(1), рекурсивный спуск (написан вручную, одна функция на нетерминал).
* **Лексер:** табличный ДКА из HW1 (`funny_lexer/`), теперь с позициями строка:столбец.
* **Выход:** AST текстовым деревом или в JSON + диагностика ошибок с позициями.
* **Ошибки:** режим паники — парсер сообщает все ошибки за один запуск и не зацикливается.

## Быстрый старт

```bash
python3 -m funny_parser all                      # проверка грамматики + все тесты парсера
python3 -m funny_parser parse examples/gcd.fn    # AST программы
python3 -m funny_parser parse examples/broken.fn # пример диагностики
```

## Команды

```bash
python3 -m funny_parser parse FILE [--json] [--partial]   # AST: дерево (по умолчанию) или JSON
python3 -m funny_parser tokens FILE                       # токены с позициями строка:столбец
python3 -m funny_parser grammar [-v]                      # LL(1): FIRST/FOLLOW, таблица, конфликты
python3 -m funny_parser test [-v]                         # тесты парсера
python3 -m funny_lexer all                                # лексер: автомат + тесты HW1
python3 -m unittest discover -s tests -v                  # всё через unittest
make all | parser | lexer | grammar | test | unittest | clean
```

* `FILE` можно заменить на `-`, тогда текст читается из терминала: `echo '...' | python3 -m funny_parser parse -`.
* `--partial` — при ошибках всё равно вывести то, что удалось разобрать.
* Код возврата: 0 — без ошибок, 1 — есть ошибки, 2 — файл не найден.

## Примеры

```
$ python3 -m funny_parser parse examples/gcd.fn
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
        Assign b = y  @9:3
        While (!= a b)  @10:3
          invariant: (and (> a 0) (> b 0))
          body:
            Block  @12:3
              If (> a b)  @13:5
                then:
                  Assign a = (- a b)  @14:7
                else:
                  Assign b = (- b a)  @16:7
        Assign r = a  @18:3
```

```
$ python3 -m funny_parser parse examples/broken.fn
examples/broken.fn:8:3: ошибка: ожидалось ';' в конце присваивания, найдено идентификатор 'b'
examples/broken.fn:9:17: ошибка: ожидалось ')' для '(' из 9:9, найдено '{'
examples/broken.fn:12:11: ошибка: ожидалось выражение, найдено ';'
examples/broken.fn:16:7: ошибка: ожидалось логическое выражение (сравнение, true/false, not/and/or), найдено: переменная
Найдено ошибок: 4; AST не выведен (флаг --partial покажет частичное дерево)
```

## Документы

| Файл | Что внутри |
|---|---|
| [`grammar/funny.ll1`](grammar/funny.ll1) | **финальная грамматика** (BNF, проверяется программой) |
| [`GRAMMAR.md`](GRAMMAR.md) | грамматика в EBNF, приоритеты, приведение к LL(1), конфликт `else`, **отклонения от спецификации**, обработка ошибок |
| [`AST.md`](AST.md) | API парсера, узлы AST, форматы JSON и текстового дерева |
| [`LEXER.md`](LEXER.md) | лексер из HW1 |

## Структура

```
funny_parser/
  tokens.py      интеграция с лексером: токены с позициями, лексические ошибки
  parser.py      ★ рекурсивный спуск по grammar/funny.ll1 + режим паники
  sortcheck.py   проверка видов выражений: целое / условие / предикат
  ast.py         узлы AST, вывод в текст и JSON
  ll1.py         проверка грамматики: FIRST, FOLLOW, LL(1)-таблица, конфликты
  testing.py     тесты парсера;  cli.py — команды
funny_lexer/     лексер из HW1 (добавлены позиции строка:столбец)
spec/funny.tokens   токены языка (HW1)
grammar/funny.ll1   грамматика (HW2)
tests/parser/
  positive/*.fn + *.ast   программы без ошибок и эталонное AST
  negative/*.fn + *.err   программы с ошибками и ожидаемые сообщения
  expr_cases.json         выражения: приоритеты, ассоциативность, виды
tests/cases.json          тесты лексера (HW1)
examples/                 примеры для ручного запуска
out/                      генерируется: таблица лексера, LL(1)-таблица, результаты тестов
```

## Интеграция с лексером

`funny_parser/tokens.py` берёт таблицу ДКА из `out/dfa.json` (если её нет или
`spec/funny.tokens` новее — пересобирает через `funny_lexer`) и запускает табличный
лексер `funny_lexer/lexer.py`. Каждый токен — `Token(kind, lexeme, pos, line, col)`;
строки и столбцы считаются с 1, `\r\n` — один перевод строки, таб — один столбец.
`WS` и `COMMENT` отбрасываются, в конце добавляется `EOF`.

## Тесты

`python3 -m funny_parser test` — 141 проверка:

| Группа | Сколько | Что проверяет |
|---|---|---|
| positive | 12 | программы со всеми конструкциями; AST сравнивается с эталоном `*.ast` |
| negative | 20 | пустой ввод, незакрытые скобки, лишние токены, неверные операторы, пропущенные `;`, ошибки в заголовке, цепочки сравнений, неверные виды выражений, лексические ошибки, восстановление после нескольких ошибок; сообщения сравниваются с `*.err` |
| expr | 82 | приоритеты и ассоциативность, условия и предикаты, ошибки в выражениях |
| positions | 9 | строка:столбец токенов (LF, CRLF, `\r`, табы, комментарии) |
| grammar | 4 | LL(1): только ожидаемый конфликт, терминалы = токены лексера |
| json | 12 | AST сериализуется в JSON |
| fuzz | 2 | 600 случайно испорченных программ: парсер не падает и не зацикливается |

Плюс 347 тестов лексера из HW1 (`python3 -m funny_lexer test`).

Эталоны можно пересоздать командой `python3 -m funny_parser test --update`, но после этого
их нужно просмотреть глазами: команда записывает то, что выдал парсер.
