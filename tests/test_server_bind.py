"""The personal API must bind locally unless explicitly configured otherwise."""

import config
import run


class FakeServer:
    addresses = []

    def __init__(self, address, app, **kwargs):
        self.addresses.append(address)

    def start(self):
        pass

    def stop(self):
        pass


def test_server_defaults_to_loopback():
    assert config.HOST == "127.0.0.1"


def test_run_uses_configured_loopback_host(monkeypatch):
    FakeServer.addresses = []
    monkeypatch.setattr(config, "HOST", "127.0.0.1", raising=False)
    monkeypatch.setattr(run.wsgi, "Server", FakeServer)

    run.main()

    assert FakeServer.addresses == [("127.0.0.1", config.PORT)]


def test_operator_can_explicitly_enable_lan_binding(monkeypatch):
    FakeServer.addresses = []
    monkeypatch.setattr(config, "HOST", "0.0.0.0", raising=False)
    monkeypatch.setattr(run.wsgi, "Server", FakeServer)

    run.main()

    assert FakeServer.addresses == [("0.0.0.0", config.PORT)]
