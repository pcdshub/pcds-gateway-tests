""""pcds-gateway-tests comparison tool"""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import ClassVar, Optional

import apischema
import whatrecord.plugins.happi as happi_plugin
from whatrecord.access_security import AccessSecurityConfig
from whatrecord.gateway import GatewayConfig

from .conftest import MODULE_PATH

DESCRIPTION = __doc__


def get_ioc_to_pvs() -> dict[str, tuple[str, str]]:
    def split_rtype(line):
        if "," in line:
            return line.split(",", 1)
        return line, "unknown"

    ioc_to_pvs = {}
    iocdata = pathlib.Path("/cds/data/iocData")
    for pvlist in iocdata.glob("*/iocInfo/IOC.pvlist"):
        ioc_name = pvlist.parts[len(iocdata.parts)]
        with open(pvlist, "rt") as fp:
            ioc_to_pvs[ioc_name] = dict(
                split_rtype(line) for line in fp.read().splitlines()
            )

    return ioc_to_pvs


def get_pv_to_ioc() -> dict[str, str]:
    return {
        pv: ioc
        for ioc, pvs in get_ioc_to_pvs().items()
        for pv in pvs
    }


class HappiInfo(happi_plugin.HappiPluginResults):
    @classmethod
    def from_json(cls, fn: str) -> HappiInfo:
        with (MODULE_PATH / "happi_info.json").open() as fp:
            happi_json = json.load(fp)

        return apischema.deserialize(cls, happi_json)

    @property
    def pvlist(self):
        return list(self.record_to_metadata_keys)


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


class PCDSConfiguration:
    _instance_: ClassVar[PCDSConfiguration]
    gateway_config: GatewayConfig
    access_security: AccessSecurityConfig
    happi_info: HappiInfo
    pv_to_ioc: dict[str, str]

    def __init__(self):
        self.gateway_config = GatewayConfig(
            path="/cds/group/pcds/gateway/config"
        )
        self.access_security = AccessSecurityConfig.from_file(
            "/cds/group/pcds/gateway/config/pcds-access.acf"
        )
        self.happi_info = HappiInfo.from_json("happi_info.json")
        self.pv_to_ioc = get_pv_to_ioc()

    @staticmethod
    def instance():
        if not hasattr(PCDSConfiguration, "_instance_"):
            PCDSConfiguration._instance_ = PCDSConfiguration()

        return PCDSConfiguration._instance_


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
