all: missing-pvs-report


happi_info.json: /cds/group/pcds/pyps/apps/hutch-python/device_config/db.json
	@echo "Updating happi_info.json based on device_config database..."
	@python -m whatrecord.plugins.happi > tests/happi_info.json


missing-pvs-report: happi_info.json
	@echo "Happi PVs which do not map to known IOCs are as follows:"
	@python tests/compare.py missing-pvs-report


.PHONY: missing-pvs-report
