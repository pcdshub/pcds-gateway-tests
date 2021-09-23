""""pcds-gateway-tests comparison tool"""

from __future__ import annotations

import argparse
from typing import Optional

from .config import PCDSConfiguration

DESCRIPTION = __doc__


def get_missing_pvs() -> dict[str, list[str]]:
    """PV to happi items, where source of PV is unknown."""
    config = PCDSConfiguration.instance()
    return {
        pv: config.happi_info.record_to_metadata_keys[pv]
        for pv in sorted(config.happi_info.pvlist)
        if pv not in config.pv_to_ioc
    }


def _build_arg_parser(parser: Optional[argparse.ArgumentParser] = None) -> argparse.ArgumentParser:
    if parser is None:
        parser = argparse.ArgumentParser()

    parser.description = DESCRIPTION
    parser.formatter_class = argparse.RawTextHelpFormatter

    parser.add_argument(
        "command",
        choices=("missing-pvs-report", ),
    )
    return parser


def missing_pvs_report():
    """Report of happi items with PVs that are not found in the IOC pvlists."""
    for pv, devices in get_missing_pvs().items():
        print(pv, ", ".join(devices))


def main():
    parser = _build_arg_parser()
    args = parser.parse_args()
    if args.command == "missing-pvs-report":
        return missing_pvs_report()


if __name__ == "__main__":
    main()
