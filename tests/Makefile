GATEWAY_ROOT ?= /cds/group/pcds/epics/extensions/gateway/R2.1.2.0-1.3.0
PYTEST_OPTIONS ?=

tests:
	GATEWAY_ROOT=$(GATEWAY_ROOT) \
		pytest -v --forked \
			$(PYTEST_OPTIONS) \
			test_cs_studio.py \
			test_dbe_alarm.py \
			test_dbe_log.py \
			test_dbe_prop.py \
			test_dbe_value.py \
			test_enum_property_cache.py \
			test_enum_undefined_timestamp.py \
			test_property_cache.py \
			test_simple.py \
			test_structures.py \
			test_waveform_with_ca_max_array_bytes.py

.PHONY: tests
