"""Fixtures comunes. Bloquea la red en todos los tests (CA-14)."""

import socket

import pytest


class NetworkBlockedError(RuntimeError):
    """Se ha intentado abrir una conexión de red real durante un test."""


def _block(*_args, **_kwargs):
    raise NetworkBlockedError("Red bloqueada en los tests: no se permiten conexiones (CA-14).")


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    monkeypatch.setattr(socket, "socket", _block)
    monkeypatch.setattr(socket, "create_connection", _block)
