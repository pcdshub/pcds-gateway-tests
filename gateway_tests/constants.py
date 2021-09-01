import pathlib

MODULE_PATH = pathlib.Path(__file__).parent.resolve()

GATEWAY_DIR = pathlib.Path("/cds/group/pcds/gateway")
GATEWAY_CFG = GATEWAY_DIR / "config"
EPICSCAGP = GATEWAY_CFG / "epicscagp"
PCDS_ACCESS = GATEWAY_CFG / "pcds-access.acf"
