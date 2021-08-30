all: missing-pvs-report

GATEWAY_ROOT ?= /cds/group/pcds/epics/extensions/gateway/R2.1.2.0-1.3.0
PYTEST_OPTIONS ?=


happi_info.json: /cds/group/pcds/pyps/apps/hutch-python/device_config/db.json
	@echo "Updating happi_info.json based on device_config database..."
	@python -m whatrecord.plugins.happi > gateway_tests/happi_info.json


missing-pvs-report: happi_info.json
	@echo "Happi PVs which do not map to known IOCs are as follows:"
	@python gateway_tests/compare.py missing-pvs-report


tests:
	GATEWAY_ROOT=$(GATEWAY_ROOT) \
			pytest -v --forked gateway_tests \
					$(PYTEST_OPTIONS)


.PHONY: missing-pvs-report tests
