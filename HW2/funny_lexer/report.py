"""Генерация REPORT.md из реального прогона (числа не вписываются руками)."""
from collections import deque

from .dfa import hopcroft_partition
from .export import class_members, describe_symbols
from .testing import summarize

GROUP_TITLES = {
    "empty": "пустая строка", "whitespace": "пробелы / табы / CRLF", "integers": "целые (0, 00, 01 …)",
    "identifiers": "идентификаторы (и запрет _)", "keywords": "ключевые слова и «почти ключевые»",
    "operators": "операторы и разделители", "comments": "комментарии //…", "trap": "ловушка (non-ASCII, мусор)",
    "program": "фрагменты программ", "alphabet": "все 128 ASCII + non-ASCII по одному",
    "property": "свойства (НКА≡ДКА≡минДКА, Хопкрофт≡Мур)",
}


def _md(s):
    return s.replace("|", "\\|")


def merged_groups(result):
    """Какие состояния ДКА склеил Хопкрофт (с кратчайшей строкой-свидетелем)."""
    d = result.dfa
    reps = {}
    for sym, c in enumerate(d.class_of):
        reps.setdefault(c, sym)
    witness, q = {d.start: ""}, deque([d.start])
    while q:
        s = q.popleft()
        for c, t in enumerate(d.trans[s]):
            if t not in witness:
                witness[t] = witness[s] + (chr(reps[c]) if reps[c] < 128 else "é")
                q.append(t)
    block_of, _ = hopcroft_partition(d)
    groups = {}
    for s in range(d.num_states):
        groups.setdefault(block_of[s], []).append(s)
    out = []
    for g in groups.values():
        if len(g) > 1:
            l = d.labels[g[0]]
            out.append((result.tokens[l].name if l is not None else "—",
                        [repr(witness[s]) for s in g]))
    return out


def render(result, results):
    st, mdfa = result.stats, result.min_dfa
    L = ["# HW1 — отчёт: регулярные выражения → ДКА → минимизация", "",
         "_Сгенерировано командой `python -m funny_lexer report`._", "",
         "## 1. Регулярные выражения", "",
         "Порядок = приоритет при равной длине; лексер — maximal munch.", "",
         "| # | Токен | Вид | Регулярное выражение |", "|---|---|---|---|"]
    for t in result.tokens:
        L.append(f"| {t.priority} | `{t.name}` | {t.kind} | `{_md(t.regex)}` |")
    L += ["", "## 2. Размеры автоматов", "",
          "| Этап | Состояний | Принимающих | Прочее |", "|---|---|---|---|",
          f"| НКА (Томпсон) | {st['nfa_states']} | {len(result.tokens)} | "
          f"ε-рёбер {st['nfa_eps_edges']}, рёбер-по-символу {st['nfa_char_edges']} |",
          f"| ДКА (subset construction) | {st['dfa_states']} | {st['dfa_accepting']} | вкл. ловушку |",
          f"| **Мин. ДКА (Хопкрофт)** | **{st['min_dfa_states']}** | **{st['min_dfa_accepting']}** | вкл. ловушку |",
          "",
          f"Алфавит: {st['alphabet_size']} символов (128 ASCII + 1 символ `OTHER` для всех кодов ≥ 128), "
          f"сжат до **{st['char_classes']} классов** эквивалентности; таблица мин. ДКА — "
          f"{st['min_dfa_states']} × {st['char_classes']}.", "",
          "Контроль корректности минимизации:",
          f"- алгоритм Мура на том же ДКА даёт {st['moore_check_states']} классов (Хопкрофт: {st['min_dfa_states']});",
          f"- мин. ДКА эквивалентен исходному ДКА (обход произведения): **{st['min_equivalent_to_dfa']}**;",
          f"- в мин. ДКА нет эквивалентных состояний: **{st['min_is_minimal']}**.", "",
          "Начальное разбиение Хопкрофта — не «принимающие / нет», а по имени токена: иначе "
          "слились бы, например, состояния после `if` (KW_IF) и после `ix` (IDENT).", "",
          "Какие состояния склеены (строка — кратчайший путь из старта в состояние ДКА):", ""]
    for name, ws in merged_groups(result):
        L.append(f"- `{name}`: после " + " ≡ ".join(f"`{_md(w)}`" for w in ws))
    L += ["",
          "Subset construction и так даёт почти минимальный автомат (токены в основном литералы), "
          "поэтому склеиваются только «первая итерация» и «последующие итерации» в `[1-9][0-9]*`, "
          "`[A-Za-z][A-Za-z0-9]*` и `//[^\\r\\n]*`.", "",
          "## 3. Ловушка", "",
          f"Состояние **{mdfa.trap}** (последнее; старт — {mdfa.start}). Непринимающее, все переходы — в себя. "
          "Автомат полный: из каждого состояния по каждому классу есть переход. В ловушку ведут:", "",
          "- из старта — любой символ, с которого не начинается ни один токен "
          "(`! @ # $ % ^ & _ ~ ? . ' \" \\` …, управляющие кроме `\\t \\n \\r`, DEL);",
          "- **любой non-ASCII** код (символ `OTHER`) — из любого состояния, даже внутри комментария;",
          "- продолжения, невозможные в языке (например `!` без `=`).", "",
          "Лексер, попав в ловушку, откатывается к последней принимающей позиции; "
          "если её не было — выдаёт `ERROR` на один символ и продолжает со следующего.", "",
          "## 4. Классы символов", "", "| Класс | Символы |", "|---|---|"]
    for i, m in enumerate(class_members(mdfa)):
        L.append(f"| c{i} | `` {_md(describe_symbols(m))} `` |")
    L += ["", "## 5. Тесты", "", "| Группа | Сценарий | PASS | FAIL |", "|---|---|---|---|"]
    total = [0, 0]
    for g, (p, f) in summarize(results).items():
        total[0] += p
        total[1] += f
        L.append(f"| {g} | {GROUP_TITLES.get(g, g)} | {p} | {f} |")
    L.append(f"| **итого** | | **{total[0]}** | **{total[1]}** |")
    L += ["", "Подробные результаты (вход, ожидание, факт, статус) — `out/test_results.json`.", ""]
    return "\n".join(L)
