"""Esqueleto del paquete y bloqueo de red."""

import importlib
import pkgutil
import socket

import pytest

import ringr_agents


def _module_names():
    return [
        m.name
        for m in pkgutil.walk_packages(ringr_agents.__path__, prefix="ringr_agents.")
        if not m.name.endswith("__main__")
    ]


def test_all_package_modules_import():
    """Estructura: todos los módulos del paquete existen y se importan."""
    names = _module_names()

    for name in names:
        importlib.import_module(name)

    assert "ringr_agents.domain.ports" in names
    assert "ringr_agents.agents.debt.agent" in names
    assert "ringr_agents.infrastructure.http.sender" in names


def test_opening_a_socket_fails_because_network_is_blocked():
    """CA-14: ningún test abre red."""
    with pytest.raises(RuntimeError, match="Red bloqueada"):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)


def test_create_connection_fails_because_network_is_blocked():
    """CA-14: create_connection también está bloqueado."""
    with pytest.raises(RuntimeError, match="Red bloqueada"):
        socket.create_connection(("example.com", 80))
