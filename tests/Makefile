GATEWAY_ROOT ?= /cds/group/pcds/epics/extensions/gateway/R2.1.2.0-1.3.0
PYTEST_OPTIONS ?=

tests:
	GATEWAY_ROOT=$(GATEWAY_ROOT) \
		pytest -v test_enum_undefined_timestamp.py $(PYTEST_OPTIONS)

.PHONY: tests
