import json
import os
import signal
from unittest.mock import MagicMock, patch

from sago.server.daemon import SagoClient, SagoDaemon, get_client, get_daemon


def test_daemon_init_and_keys(tmp_path):
    with patch("sago.server.daemon.AUTH_FILE", tmp_path / "daemon.key"):
        daemon = SagoDaemon(host="127.0.0.1", port=9999)
        assert daemon._api_key is not None
        assert daemon._verify_api_key(daemon._api_key) is True
        assert daemon._verify_api_key("wrong_key") is False
        assert daemon._verify_api_key("") is False


def test_daemon_pid_and_running(tmp_path):
    pid_file = tmp_path / "daemon.pid"
    daemon = SagoDaemon()
    daemon.pid_file = pid_file

    assert daemon.is_running() is False
    assert daemon.get_pid() is None

    # Write current pid
    pid_file.write_text(str(os.getpid()))
    assert daemon.is_running() is True
    assert daemon.get_pid() == os.getpid()

    # Write stale pid
    pid_file.write_text("99999999")
    assert daemon.is_running() is False


def test_daemon_process_request():
    daemon = SagoDaemon(api_key="secret")
    # Ping
    ping_res = daemon._process_request({"action": "ping"})
    assert ping_res["status"] == "ok"

    # Status
    status_res = daemon._process_request({"action": "status"})
    assert status_res["status"] == "running"
    assert status_res["api_key_set"] is True

    # Peers
    with patch("sago.peers.manager.PeerManager") as mock_pm_cls:
        mock_pm = MagicMock()
        mock_peer = MagicMock()
        mock_peer.to_dict.return_value = {"id": "peer1", "name": "Peer 1"}
        mock_pm.list_peers.return_value = [mock_peer]
        mock_pm_cls.return_value = mock_pm

        peers_res = daemon._process_request({"action": "peers"})
        assert len(peers_res["peers"]) == 1

    # Stop
    stop_res = daemon._process_request({"action": "stop"})
    assert stop_res["status"] == "stopping"
    assert daemon._running is False

    # Unknown
    unknown_res = daemon._process_request({"action": "nonexistent_action"})
    assert "error" in unknown_res


def test_daemon_execute_task(monkeypatch):
    daemon = SagoDaemon()
    # No API key
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    res_no_key = daemon._execute_task("Do something")
    assert res_no_key["status"] == "failed"
    assert "No API key" in res_no_key["error"]

    # Success with API key
    monkeypatch.setenv("OPENROUTER_API_KEY", "mock_key")
    with patch("sago.engine.simple_executor.execute_agent_task") as mock_exec:
        mock_exec.return_value = {
            "output": "Task result",
            "tool_calls": ["c1"],
            "tokens": {"input": 1, "output": 2},
            "elapsed": 0.1,
        }
        res_ok = daemon._execute_task("Do something")
        assert res_ok["status"] == "completed"
        assert res_ok["result"] == "Task result"


def test_daemon_handle_client():
    daemon = SagoDaemon(api_key="valid_key")

    # 1. Valid request
    client_valid = MagicMock()
    req_bytes = json.dumps({"action": "ping", "api_key": "valid_key"}).encode() + b"\n"
    client_valid.recv.side_effect = [req_bytes, b""]
    daemon._handle_client(client_valid)
    client_valid.send.assert_called()
    sent_data = json.loads(client_valid.send.call_args[0][0].decode())
    assert sent_data["status"] == "ok"

    # 2. Invalid auth
    client_unauth = MagicMock()
    req_unauth = json.dumps({"action": "ping", "api_key": "bad_key"}).encode() + b"\n"
    client_unauth.recv.side_effect = [req_unauth, b""]
    daemon._handle_client(client_unauth)
    sent_unauth = json.loads(client_unauth.send.call_args[0][0].decode())
    assert "Unauthorized" in sent_unauth["error"]

    # 3. Payload too large
    client_big = MagicMock()
    client_big.recv.return_value = b"x" * 1_000_001
    daemon._handle_client(client_big)
    sent_big = json.loads(client_big.send.call_args[0][0].decode())
    assert "too large" in sent_big["error"]

    # 4. Invalid JSON
    client_invalid = MagicMock()
    client_invalid.recv.side_effect = [b"not a valid json\n", b""]
    daemon._handle_client(client_invalid)
    sent_inv = json.loads(client_invalid.send.call_args[0][0].decode())
    assert "Invalid JSON" in sent_inv["error"]


def test_daemon_signals_and_status():
    daemon = SagoDaemon()
    daemon._running = True
    daemon._handle_signal(signal.SIGINT, None)
    assert daemon._running is False

    assert "Not running" in daemon.status()


def test_sago_client(tmp_path):
    with patch("sago.server.daemon.AUTH_FILE", tmp_path / "daemon.key"):
        (tmp_path / "daemon.key").write_text("my_client_key")
        client = SagoClient(api_key="override_key")
        assert client.api_key == "override_key"

        with patch.object(client, "_send") as mock_send:
            mock_send.return_value = {"status": "ok"}
            assert client.ping() is True

            mock_send.return_value = {"status": "completed", "result": "done"}
            res = client.execute("task1")
            assert res["status"] == "completed"

            mock_send.return_value = {"status": "running"}
            st = client.status()
            assert st["status"] == "running"

            mock_send.return_value = {"status": "stopping"}
            stop = client.stop_daemon()
            assert stop["status"] == "stopping"


def test_get_daemon_and_client():
    d = get_daemon()
    assert isinstance(d, SagoDaemon)
    c = get_client()
    assert isinstance(c, SagoClient)


def test_sago_client_send_socket():
    client = SagoClient(api_key="my_key")
    with patch("socket.socket") as mock_socket_cls:
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock

        # Success
        mock_sock.recv.side_effect = [json.dumps({"status": "ok"}).encode() + b"\n"]
        res = client._send({"action": "ping"})
        assert res["status"] == "ok"

        # Connection refused
        import pytest

        mock_sock.connect.side_effect = ConnectionRefusedError()
        with pytest.raises(ConnectionError, match="Daemon not running"):
            client._send({"action": "ping"})


def test_daemon_stop(tmp_path):
    daemon = SagoDaemon()
    daemon.pid_file = tmp_path / "daemon.pid"

    # Already stopped
    assert daemon.stop() is True

    # Process exists, kill graceful
    daemon.pid_file.write_text("12345")
    with (
        patch.object(daemon, "is_running", side_effect=[True, False]),
        patch("os.kill") as mock_kill,
    ):
        assert daemon.stop() is True
        mock_kill.assert_called_with(12345, signal.SIGTERM)


def test_daemon_server_loop():
    daemon = SagoDaemon()
    with patch("socket.socket") as mock_socket_cls:
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock

        def mock_accept():
            daemon._running = False
            client_mock = MagicMock()
            client_mock.recv.side_effect = [
                json.dumps({"action": "ping", "api_key": daemon._api_key}).encode() + b"\n"
            ]
            return client_mock, ("127.0.0.1", 12345)

        mock_sock.accept.side_effect = mock_accept
        daemon._run_server()
        assert daemon._running is False


def test_daemon_restart():
    daemon = SagoDaemon()
    with (
        patch.object(daemon, "stop") as mock_stop,
        patch.object(daemon, "start") as mock_start,
        patch("time.sleep"),
    ):
        daemon.restart()
        mock_stop.assert_called_once()
        mock_start.assert_called_once()


def test_daemon_connection_limit():
    daemon = SagoDaemon(max_connections=1)
    daemon._active_connections = 1
    with patch("socket.socket") as mock_socket_cls:
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock

        calls = [0]

        def mock_accept():
            calls[0] += 1
            if calls[0] == 1:
                client_mock = MagicMock()
                return client_mock, ("127.0.0.1", 54321)
            daemon._running = False
            raise TimeoutError()

        mock_sock.accept.side_effect = mock_accept
        daemon._run_server()


def test_sago_client_empty_response():
    client = SagoClient()
    with patch("socket.socket") as mock_socket_cls:
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        mock_sock.recv.return_value = b""
        import pytest

        with pytest.raises(ConnectionError, match="Daemon returned empty response"):
            client._send({"action": "ping"})


def test_daemon_start_foreground():
    daemon = SagoDaemon()
    with (
        patch.object(daemon, "is_running", side_effect=[False, True]),
        patch.object(daemon, "_run_server"),
        patch("builtins.print"),
    ):
        daemon.start(foreground=True)
        assert daemon.status().startswith("Running")
