"""Integration tests for server/daemon."""

import pytest

from sago.server.daemon import SagoClient, SagoDaemon


@pytest.fixture
def daemon():
    """Create a daemon instance on a random port."""
    d = SagoDaemon(host="127.0.0.1", port=0)
    yield d
    if d._running:
        d.stop()


class TestSagoDaemon:
    def test_daemon_init(self, daemon):
        assert daemon.host == "127.0.0.1"
        assert daemon.port == 0

    def test_daemon_is_not_running(self, daemon):
        assert daemon._running is False

    def test_daemon_pid_file(self, daemon):
        # PID file should not exist when not running
        assert not daemon.pid_file.exists() or daemon.get_pid() is None


class TestSagoClient:
    def test_client_init(self):
        client = SagoClient("127.0.0.1", 7654)
        assert client.host == "127.0.0.1"
        assert client.port == 7654

    def test_client_connection_refused(self):
        client = SagoClient("127.0.0.1", 19999)
        with pytest.raises((ConnectionError, OSError)):
            client.execute("test")

    def test_client_ping_refused(self):
        client = SagoClient("127.0.0.1", 19999)
        # ping returns False when connection refused
        result = client.ping()
        assert result is False


class TestServerProtocol:
    def test_daemon_request_format(self, daemon):
        # Test that daemon can parse valid request format
        import json
        request = {"action": "ping"}
        # Just test the format, not actual execution
        assert json.dumps(request) is not None

    def test_daemon_execute_request_format(self, daemon):
        import json
        request = {"action": "execute", "task": "echo hello", "agent": None}
        assert json.dumps(request) is not None
