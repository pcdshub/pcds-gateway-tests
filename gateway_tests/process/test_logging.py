from __future__ import annotations

import contextlib
import dataclasses
import datetime
import logging
import socket
import tempfile
import threading
from typing import Any, ContextManager, Optional

import pytest

from .. import conftest

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def listen_on_port(port, encoding="latin-1") -> ContextManager[list[str]]:
    """Listen on TCP port `port` for caPutLog data."""
    data = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('127.0.0.1', port))

    def listen():
        sock.listen(1)
        client, addr = sock.accept()
        logger.warning("TCP accepted client %s", addr)
        while True:
            read = client.recv(4096)
            logger.info("caPutLog TCP server received %s", read)
            if not data:
                client.close()
                return
            data.append(read.decode(encoding))

    threading.Thread(target=listen, daemon=True).start()
    yield data
    sock.close()


@dataclasses.dataclass
class Caput:
    """A single caputlog line, parsed into its parts."""
    date: datetime.datetime
    user: str
    host: str
    pvname: str
    value: str
    old: Optional[str] = None

    @classmethod
    def from_line(cls, line: str) -> Caput:
        parts = line.split(" ")
        logger.info("parts %s", parts)
        user, host = parts[3].split("@")
        # We'll make a point of not using such strings in our values, OK?
        if " old=" in line:
            value, old = " ".join(parts[5:]).split(" old=")
        else:
            value, old = parts[5:], None

        return cls(
            date=datetime.datetime.strptime(
                " ".join(parts[:3]),
                "%b %d %H:%M:%S"
            ).replace(year=datetime.datetime.now().year),
            user=user,
            host=host,
            pvname=parts[4],
            value=value,
            old=old,
        )


@dataclasses.dataclass
class CaputLog:
    """An entire caputlog."""
    header: list[str]
    puts: list[Caput]

    @classmethod
    def from_string(cls, contents: str) -> CaputLog:
        """Parse a caputlog file contents into a CaputLog instance."""
        lines = contents.splitlines()
        try:
            attempted_writes_idx = lines.index("Attempted Writes:")
        except ValueError:
            raise RuntimeError(f"Invalid caputlog? Lines: {lines}")

        header, puts = lines[:attempted_writes_idx], lines[attempted_writes_idx + 1:]
        logger.info("caputlog header:\n%s", "\n".join(header))
        logger.info("Puts:\n%s", "\n".join(puts))
        return cls(
            header=header,
            puts=[Caput.from_line(line) for line in puts],
        )

    @classmethod
    def from_bytes(cls, raw: bytes) -> CaputLog:
        """Parse a raw caputlog file contents into a CaputLog instance."""
        return cls.from_string(raw.decode("latin-1"))


@pytest.mark.parametrize(
    "access_contents, pvlist_contents",
    [
        pytest.param(
            """\
            ASG(DEFAULT) {
                RULE(1,READ)
                RULE(1,WRITE,TRAPWRITE)
            }
            """,
            """\
            EVALUATION ORDER ALLOW, DENY
            .* ALLOW DEFAULT
            """,
            id="minimal",
        ),
    ]
)
@pytest.mark.parametrize(
    "pvname, values",
    [
        pytest.param("ioc:HUGO:AI", [0.2, 1.2]),
        pytest.param("ioc:HUGO:ENUM", [1, 2]),
        pytest.param("ioc:enumtest", [1, 2]),
        pytest.param("ioc:gwcachetest", [-20, 0, 20]),
        pytest.param("ioc:passive0", [1, 21]),
        pytest.param("ioc:passiveADEL", [1, 20]),
        pytest.param("ioc:passiveADELALRM", [1, 20]),
        pytest.param("ioc:passiveALRM", [1, 5, 10]),
        pytest.param("ioc:passiveMBBI", [1, 2]),
        pytest.param("ioc:passivelongin", [1, 2]),
        pytest.param("ioc:bigpassivewaveform", [[1, 2, 3], [4, 5, 6]]),
    ]
)
def test_caputlog(
    access_contents: str, pvlist_contents: str, pvname: str, values: list[Any]
):
    """
    Test that caPutLog works by putting to a PV and checking the output.
    """
    caputlog_port = 45634  # TODO arbitrary
    with tempfile.NamedTemporaryFile() as caputlog_fp:
        with listen_on_port(caputlog_port) as tcp_data:
            with conftest.custom_environment(
                access_contents,
                pvlist_contents,
                gateway_args=[
                    "-putlog", caputlog_fp.name,
                    "-caputlog", f"127.0.0.1:{caputlog_port}",
                ],
            ):
                with conftest.gateway_channel_access_env():
                    # Time for initial monitor event
                    for value in values:
                        conftest.pyepics_caput(pvname, value)

        caputlog_fp.seek(0)
        caputlog_raw = caputlog_fp.read()

    caputlog = CaputLog.from_bytes(caputlog_raw)

    # TCP caputlog doesn't appear functional; leave in for future usage?
    logger.info("TCP data was:\n%s", tcp_data)
    logger.info("CaputLog:\n%s", caputlog)
    for put, value in zip(caputlog.puts, values):
        assert put.pvname == pvname
        assert put.value == str(value)

    assert len(caputlog.puts) == len(values)
