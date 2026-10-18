PY ?= python3

.PHONY: all lexer parser grammar test unittest clean
all:      lexer parser
lexer:    ; $(PY) -m funny_lexer all
parser:   ; $(PY) -m funny_parser all
grammar:  ; $(PY) -m funny_parser grammar
test:     ; $(PY) -m funny_lexer test && $(PY) -m funny_parser test
unittest: ; $(PY) -m unittest discover -s tests -v
clean:    ; rm -rf out REPORT.md __pycache__ */__pycache__ tests/__pycache__
