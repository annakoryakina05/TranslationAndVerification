"""HW2: LL(1)-парсер Funny (рекурсивный спуск) поверх табличного лексера из HW1.

API:
    from funny_parser import parse_program, to_text, to_json
    module, diagnostics = parse_program(source_text)
"""
from .ast import to_json, to_text  # noqa: F401
from .parser import parse_expression, parse_program  # noqa: F401
