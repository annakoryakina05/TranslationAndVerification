"""HW3: семантический анализ Funny — имена, области видимости, типы, вывод типов локальных.

API:
    from funny_sema import check_program
    result = check_program(text)        # result.module (аннотированный AST), .tables, .diags
"""
from .pipeline import check_program  # noqa: F401
