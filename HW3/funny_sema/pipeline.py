"""Полный конвейер HW3: текст -> лексер -> парсер -> семантический анализ."""
from funny_parser.parser import parse_program

from .checker import SemaResult, analyze


def check_program(text, allow_array_locals=False):
    """Возвращает SemaResult: аннотированный AST, таблицы символов, диагностики.

    Если есть лексические/синтаксические ошибки, семантический анализ не запускается:
    дерево неполное, и проверка имён дала бы ложные ошибки («неизвестная функция»
    для функции, которую парсер пропустил). Внутри семантики ошибки собираются все.
    """
    first = text.split("\n", 1)[0]
    if first.startswith("// sema:") and "allow-array-locals" in first:
        allow_array_locals = True            # флаг можно задать первой строкой файла
    module, diags = parse_program(text, check_sorts=False)
    if diags:
        return SemaResult(module, {}, {}, diags)
    return analyze(module, allow_array_locals)
