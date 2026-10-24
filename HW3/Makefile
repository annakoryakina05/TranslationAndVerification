PY ?= python3

.PHONY: test sema parser lexer unittest clean
test:     lexer parser sema
sema:     ; $(PY) -m funny_sema test
parser:   ; $(PY) -m funny_parser all
lexer:    ; $(PY) -m funny_lexer all
unittest: ; $(PY) -m unittest discover -s tests -v
clean:    ; rm -rf out REPORT.md __pycache__ */__pycache__ tests/__pycache__
