all: tests

GATEWAY_ROOT ?= /cds/group/pcds/epics/extensions/gateway/R2.1.2.0-1.3.0
PYTEST_OPTIONS ?=
DEVICE_CONFIG_DB ?= /cds/group/pcds/pyps/apps/hutch-python/device_config/db.json


gateway_tests/happi_info.json: $(DEVICE_CONFIG_DB)
	@echo "Updating happi_info.json based on device_config database..."
	@python -m whatrecord.plugins.happi > $@


missing-pvs-report: gateway_tests/happi_info.json
	@echo "Happi PVs which do not map to known IOCs are as follows:"
	GATEWAY_ROOT=$(GATEWAY_ROOT) \
		python -m gateway_tests.compare missing-pvs-report


tests: gateway_tests/happi_info.json
	GATEWAY_ROOT=$(GATEWAY_ROOT) \
			pytest -v --forked gateway_tests \
					$(PYTEST_OPTIONS)


.PHONY: missing-pvs-report tests
