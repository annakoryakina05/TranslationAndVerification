"""Полный конвейер: спецификация → НКА → ДКА → минимальный ДКА."""
from dataclasses import dataclass

from .dfa import compute_char_classes, equivalent, minimize, moore_count, subset_construction
from .nfa import build_nfa
from .spec import load_spec


@dataclass
class BuildResult:
    tokens: list
    nfa: object
    dfa: object        # после subset construction
    min_dfa: object    # после Хопкрофта
    stats: dict


def build(spec_path=None):
    tokens = load_spec(spec_path)
    nfa = build_nfa(tokens)
    class_of, reps = compute_char_classes(nfa)
    dfa, _ = subset_construction(nfa, class_of, reps)
    mdfa = minimize(dfa)
    stats = {
        "tokens": len(tokens),
        "nfa_states": nfa.num_states,
        "nfa_eps_edges": nfa.num_eps_edges,
        "nfa_char_edges": nfa.num_char_edges,
        "alphabet_size": len(class_of),
        "char_classes": len(reps),
        "dfa_states": dfa.num_states,
        "dfa_accepting": dfa.num_accepting,
        "min_dfa_states": mdfa.num_states,
        "min_dfa_accepting": mdfa.num_accepting,
        "min_dfa_trap": mdfa.trap,
        "moore_check_states": moore_count(dfa),
        "min_equivalent_to_dfa": equivalent(dfa, mdfa),
        "min_is_minimal": moore_count(mdfa) == mdfa.num_states,
    }
    return BuildResult(tokens, nfa, dfa, mdfa, stats)
