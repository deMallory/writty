"""Shared test helper: obtain an unused local TCP port.

Consolidates the _free_port helper formerly duplicated in five test
modules (Wave-5 Cycle 5.3a). Binds an ephemeral 127.0.0.1 socket, reads
the OS-assigned port, closes, and returns it.
"""
from __future__ import annotations

import socket


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port
