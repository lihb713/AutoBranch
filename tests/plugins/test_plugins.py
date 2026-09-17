"""预置插件（compute / file / ssh）单元测试（组 5）。"""

from __future__ import annotations

import sys
import types

from autobranch.plugin_system import PluginRegistry
from autobranch.plugins.compute import ComputePlugin
from autobranch.plugins.file import FileDiff, FilePlugin
from autobranch.plugins.ssh import SSHConnection, SSHPlugin

# ------------------------------------------------------------ compute


def _compute_reg():
    reg = PluginRegistry()
    reg.register(ComputePlugin())
    return reg


def test_compute_multiply():
    assert _compute_reg().call("compute.multiply", {"a": 2, "b": 3}).value == 6


def test_compute_sort():
    assert _compute_reg().call("compute.sort", {"data": [3, 1, 2]}).value == [1, 2, 3]
    assert _compute_reg().call("compute.sort", {"data": [3, 1, 2], "desc": True}).value == [3, 2, 1]


def test_compute_compare():
    assert _compute_reg().call("compute.compare", {"a": 5, "b": 3}).value is True
    assert _compute_reg().call("compute.compare", {"a": 3, "b": 5}).value is False


def test_compute_add():
    assert _compute_reg().call("compute.add", {"a": 2, "b": 3}).value == 5


def test_compute_sum():
    assert _compute_reg().call("compute.sum", {"values": [1, 2, 3]}).value == 6.0


# ------------------------------------------------------------ file


def test_file_read_write(tmp_path):
    reg = PluginRegistry()
    reg.register(FilePlugin())
    a = tmp_path / "a.txt"
    a.write_text("hello", encoding="utf-8")
    assert reg.call("file.read", {"path": str(a)}).value == "hello"
    b = tmp_path / "b.txt"
    assert reg.call("file.write", {"path": str(b), "content": "world"}).ok
    assert b.read_text(encoding="utf-8") == "world"


def test_file_read_missing_returns_error(tmp_path):
    reg = PluginRegistry()
    reg.register(FilePlugin())
    result = reg.call("file.read", {"path": str(tmp_path / "nope.txt")})
    assert not result.ok


def test_file_diff(tmp_path):
    reg = PluginRegistry()
    reg.register(FilePlugin())
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("x\ny", encoding="utf-8")
    b.write_text("x\ny", encoding="utf-8")
    same = reg.call("file.diff", {"file_a": str(a), "file_b": str(b)})
    assert same.ok and same.value.same is True
    b.write_text("x\nZ", encoding="utf-8")
    diff = reg.call("file.diff", {"file_a": str(a), "file_b": str(b)})
    assert diff.ok and diff.value.same is False
    assert isinstance(diff.value, FileDiff)


# ------------------------------------------------------------ ssh


class _FakeChannel:
    def recv_exit_status(self):
        return 0


class _FakeStream:
    def __init__(self, text: str) -> None:
        self._text = text
        self.channel = _FakeChannel()

    def read(self) -> bytes:
        return self._text.encode("utf-8")


class _FakeClient:
    def __init__(self) -> None:
        self.closed = False
        self.connected = False

    def set_missing_host_key_policy(self, policy):
        self.policy = policy

    def connect(self, **kwargs):
        self.connected = True
        self.connect_kwargs = kwargs

    def exec_command(self, command, timeout=None):
        self.last_command = command
        return None, _FakeStream("hi\n"), _FakeStream("")

    def close(self):
        self.closed = True


def _install_fake_paramiko(monkeypatch):
    fake = types.ModuleType("paramiko")
    fake.SSHClient = _FakeClient
    fake.AutoAddPolicy = lambda: None
    monkeypatch.setitem(sys.modules, "paramiko", fake)


def test_ssh_session_and_exec(monkeypatch):
    _install_fake_paramiko(monkeypatch)
    reg = PluginRegistry()
    reg.register(SSHPlugin())
    session = reg.call(
        "ssh.create_session", {"host": "192.168.1.10", "port": 22, "user": "root", "pwd": "x"}
    )
    assert session.ok
    assert isinstance(session.value, SSHConnection)
    out = reg.call("ssh.ssh_exec", {"session": session.value, "command": "echo hi"})
    assert out.ok
    assert out.values[0] == "hi\n"
    assert out.values[2] == 0
    closed = reg.call("ssh.close_session", {"session": session.value})
    assert closed.ok


def test_ssh_exec_unknown_session_fails(monkeypatch):
    _install_fake_paramiko(monkeypatch)
    reg = PluginRegistry()
    reg.register(SSHPlugin())
    result = reg.call(
        "ssh.ssh_exec",
        {"session": SSHConnection(id="nope", client=_FakeClient()), "command": "x"},
    )
    assert not result.ok


def test_ssh_release_closes_sessions(monkeypatch):
    _install_fake_paramiko(monkeypatch)
    reg = PluginRegistry()
    reg.register(SSHPlugin())
    session = reg.call("ssh.create_session", {"host": "h"})
    client = session.value.client
    reg.release()
    assert client.closed
