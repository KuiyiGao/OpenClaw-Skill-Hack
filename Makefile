.PHONY: install test clean

PYTHON ?= python

install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest tests/unit/ -q

clean:
	rm -rf build dist *.egg-info
	find . -name __pycache__ -type d -exec rm -rf {} +
