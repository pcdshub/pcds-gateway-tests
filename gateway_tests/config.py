from __future__ import annotations

import json
import pathlib
from typing import ClassVar

import apischema
import whatrecord.plugins.happi as happi_plugin
from whatrecord.access_security import AccessSecurityConfig
from whatrecord.gateway import GatewayConfig

from .constants import EPICSCAGP, GATEWAY_CFG, MODULE_PATH, PCDS_ACCESS
from .interface import InterfaceConfig


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


class PCDSConfiguration:
    _instance_: ClassVar[PCDSConfiguration]
    gateway_config: GatewayConfig
    access_security: AccessSecurityConfig
    interface_config: InterfaceConfig
    happi_info: HappiInfo
    pv_to_ioc: dict[str, str]

    def __init__(self):
        self.gateway_config = GatewayConfig(
            path=str(GATEWAY_CFG)
        )
        self.access_security = AccessSecurityConfig.from_file(
            str(PCDS_ACCESS)
        )
        self.interface_config = InterfaceConfig(
            EPICSCAGP
        )
        self.happi_info = HappiInfo.from_json("happi_info.json")
        self.pv_to_ioc = get_pv_to_ioc()

    @staticmethod
    def instance():
        if not hasattr(PCDSConfiguration, "_instance_"):
            PCDSConfiguration._instance_ = PCDSConfiguration()

        return PCDSConfiguration._instance_
