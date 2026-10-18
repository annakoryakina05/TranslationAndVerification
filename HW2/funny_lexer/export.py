"""Сериализация автомата: JSON и CSV."""
import csv
import json
from pathlib import Path

from .regex import ALPHABET_SIZE, ASCII_SIZE, OTHER

FORMAT = "funny-dfa/1"


def char_repr(sym):
    if sym == OTHER:
        return "<non-ASCII>"
    special = {9: "\\t", 10: "\\n", 13: "\\r", 32: "' '", 92: "\\\\"}
    if sym in special:
        return special[sym]
    if 33 <= sym <= 126:
        return chr(sym)
    return f"\\x{sym:02x}"


def describe_symbols(syms):
    """[97..122, 95] -> 'a-z _'"""
    syms = sorted(syms)
    out, i = [], 0
    while i < len(syms):
        j = i
        while j + 1 < len(syms) and syms[j + 1] == syms[j] + 1 and syms[j + 1] != OTHER:
            j += 1
        if j - i >= 2:
            out.append(f"{char_repr(syms[i])}-{char_repr(syms[j])}")
        else:
            out.extend(char_repr(s) for s in syms[i:j + 1])
        i = j + 1
    return " ".join(out)


def class_members(dfa):
    members = [[] for _ in range(dfa.num_classes)]
    for sym, c in enumerate(dfa.class_of):
        members[c].append(sym)
    return members


def table_dict(result, dfa=None):
    dfa = dfa or result.min_dfa
    toks = result.tokens
    return {
        "format": FORMAT,
        "alphabet": {
            "size": ALPHABET_SIZE,
            "ascii_size": ASCII_SIZE,
            "other_symbol": OTHER,
            "note": "символ с кодом >= 128 отображается в other_symbol",
        },
        "tokens": [{"name": t.name, "kind": t.kind, "priority": t.priority, "regex": t.regex}
                   for t in toks],
        "num_states": dfa.num_states,
        "num_classes": dfa.num_classes,
        "start": dfa.start,
        "trap": dfa.trap,
        "char_classes": dfa.class_of,
        "class_descriptions": [describe_symbols(m) for m in class_members(dfa)],
        "accepting": {str(s): toks[l].name for s, l in enumerate(dfa.labels) if l is not None},
        "transitions": dfa.trans,
        "stats": result.stats,
    }


def write_json(table, path):
    # компактно: одна строка таблицы — одна строка файла
    rows = ",\n    ".join(json.dumps(r) for r in table["transitions"])
    head = dict(table, transitions="__ROWS__")
    text = json.dumps(head, ensure_ascii=False, indent=2)
    text = text.replace('"__ROWS__"', "[\n    " + rows + "\n  ]")
    Path(path).write_text(text + "\n", encoding="utf-8")


def write_csv(result, path, dfa=None):
    dfa = dfa or result.min_dfa
    descr = [describe_symbols(m) for m in class_members(dfa)]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["state", "token", "kind", "note"] + [f"c{i}: {d}" for i, d in enumerate(descr)])
        for s, row in enumerate(dfa.trans):
            l = dfa.labels[s]
            tok = result.tokens[l] if l is not None else None
            note = "start" if s == dfa.start else ("trap" if s == dfa.trap else "")
            w.writerow([s, tok.name if tok else "", tok.kind if tok else "", note] + row)


def write_char_classes_csv(dfa, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["code", "char", "class"])
        for sym, c in enumerate(dfa.class_of):
            w.writerow([sym if sym != OTHER else ">=128", char_repr(sym), c])


def write_all(result, outdir):
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    table = table_dict(result)
    write_json(table, out / "dfa.json")
    write_json(table_dict(result, result.dfa), out / "dfa_unminimized.json")
    write_csv(result, out / "transitions.csv")
    write_char_classes_csv(result.min_dfa, out / "char_classes.csv")
    (out / "stats.json").write_text(json.dumps(result.stats, indent=2) + "\n", encoding="utf-8")
    return sorted(p.name for p in out.iterdir())
