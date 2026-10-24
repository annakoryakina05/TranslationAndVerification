from funny_parser.parser import parse_program

from .checker import SemaResult, analyze


def check_program(text, allow_array_locals=False):
    first = text.split("\n", 1)[0]
    if first.startswith("// sema:") and "allow-array-locals" in first:
        allow_array_locals = True            
    module, diags = parse_program(text, check_sorts=False)
    if diags:
        return SemaResult(module, {}, {}, diags)
    return analyze(module, allow_array_locals)
