.PHONY: install test code-pdf clean docs

PYTHON ?= python

install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest tests/unit/ -q

# Compile docs/code.pdf with XeLaTeX (via tectonic).
# Run this after any change to the firewall package to keep the companion
# document in sync with the source.
code-pdf docs:
	@command -v tectonic >/dev/null 2>&1 || { \
	  echo "tectonic not installed — get it from https://tectonic-typesetting.github.io/install.html"; \
	  exit 1; }
	cd docs && tectonic -X compile code.tex
	@echo "wrote docs/code.pdf"

clean:
	rm -f docs/code.pdf docs/code.aux docs/code.log docs/code.out docs/code.toc
	rm -rf build dist *.egg-info
	find . -name __pycache__ -type d -exec rm -rf {} +
