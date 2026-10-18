PY ?= python3

.PHONY: all build test report unittest clean
all:      ; $(PY) -m funny_lexer all
build:    ; $(PY) -m funny_lexer build
test:     ; $(PY) -m funny_lexer test
report:   ; $(PY) -m funny_lexer report
unittest: ; $(PY) -m unittest discover -s tests -v
clean:    ; rm -rf out __pycache__ funny_lexer/__pycache__ tests/__pycache__
