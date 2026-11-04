PYTHON ?= python

.PHONY: dev test

dev:
	$(PYTHON) -m scripts.dev

test:
	$(PYTHON) -m scripts.test_suite
