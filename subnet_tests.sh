#!/bin/bash
for subnet in las lfe tmo kfe rix xpp xcs cxi mec mfx; do
  echo "Testing subnet ${subnet}"
  export PYTEST_GATEWAY_SUBNETS="${subnet}"
  pytest --tb=line -ra -n 8 gateway_tests/prod_config/test_by_subnet.py
done
