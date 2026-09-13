import socket

import pytest


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("MAIDA_DATA_DIR", str(tmp_path / "maida"))
    monkeypatch.setenv("USER", "smoke-fixture")
    monkeypatch.setenv("LOGNAME", "smoke-fixture")

    def no_network(*args, **kwargs):
        raise AssertionError("The sales fixture must not open network connections")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket.socket, "connect", no_network)
