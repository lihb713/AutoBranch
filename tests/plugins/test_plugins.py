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


def _file_reg(tmp_path):
    reg = PluginRegistry()
    reg.register(FilePlugin(storage_dir=str(tmp_path)))
    return reg


def test_file_read_write_is_confined_to_platform_root(tmp_path):
    reg = _file_reg(tmp_path)
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    assert reg.call("file.read", {"path": "a.txt"}).value == "hello"
    assert reg.call("file.write", {"path": "sub/b.txt", "content": "world"}).ok
    assert (tmp_path / "sub" / "b.txt").read_text(encoding="utf-8") == "world"
    assert not reg.call("file.read", {"path": "../outside.txt"}).ok
    assert not reg.call("file.read", {"path": str(tmp_path / "a.txt")}).ok


def test_file_md5(tmp_path):
    reg = _file_reg(tmp_path)
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    result = reg.call("file.md5", {"path": "a.txt"})
    assert result.value == "5d41402abc4b2a76b9719d911017c592"


def test_file_read_missing_returns_error(tmp_path):
    reg = _file_reg(tmp_path)
    result = reg.call("file.read", {"path": "nope.txt"})
    assert not result.ok


def test_file_diff(tmp_path):
    reg = _file_reg(tmp_path)
    (tmp_path / "a.txt").write_text("x\ny", encoding="utf-8")
    (tmp_path / "b.txt").write_text("x\ny", encoding="utf-8")
    same = reg.call("file.diff", {"file_a": "a.txt", "file_b": "b.txt"})
    assert same.ok and same.value.same is True
    (tmp_path / "b.txt").write_text("x\nZ", encoding="utf-8")
    diff = reg.call("file.diff", {"file_a": "a.txt", "file_b": "b.txt"})
    assert diff.ok and diff.value.same is False
    assert isinstance(diff.value, FileDiff)


# ------------------------------------------------------------ ssh


class _FakeChannel:
    def __init__(
        self,
        chunks: list[bytes] | None = None,
        *,
        exit_code: int = 0,
        exit_ready: bool = True,
    ) -> None:
        self._chunks = list(chunks or [])
        self._err_chunks: list[bytes] = []
        self.exit_code = exit_code
        self._exit_ready = exit_ready
        self.sent: list[bytes] = []
        self.closed = False

    def recv_ready(self) -> bool:
        return bool(self._chunks)

    def recv(self, _size: int) -> bytes:
        return self._chunks.pop(0)

    def recv_stderr_ready(self) -> bool:
        return bool(self._err_chunks)

    def recv_stderr(self, _size: int) -> bytes:
        return self._err_chunks.pop(0)

    def exit_status_ready(self) -> bool:
        return self._exit_ready and not self._chunks and not self._err_chunks

    def recv_exit_status(self) -> int:
        return self.exit_code

    def sendall(self, data: bytes) -> None:
        self.sent.append(data)

    def close(self) -> None:
        self.closed = True


class _FakeStream:
    def __init__(self, channel: _FakeChannel) -> None:
        self.channel = channel

    def write(self, text: str) -> None:
        self.channel.sent.append(text.encode("utf-8"))

    def flush(self) -> None:
        pass


class _FakeShell:
    def __init__(self) -> None:
        self._chunks: list[bytes] = []
        self.sent: list[str] = []
        self.closed = False

    def recv_ready(self) -> bool:
        return bool(self._chunks)

    def recv(self, _size: int) -> bytes:
        return self._chunks.pop(0)

    def recv_stderr_ready(self) -> bool:
        return False

    def recv_stderr(self, _size: int) -> bytes:
        return b""

    def sendall(self, data: str | bytes) -> None:
        text = data.decode() if isinstance(data, bytes) else data
        self.sent.append(text)
        if text.startswith("ssh "):
            self._chunks.append(b"target password: ")
        elif text.strip() == "target-pwd":
            self._chunks.append(b"Last login\r\nuser@target:~$ ")
        elif "__AB_START_" in text:
            import re
            match = re.search(r"__AB_START_([0-9a-f]+)__", text)
            if match:
                token = match.group(1)
                code = 2 if "false" in text else 0
                output = b"YWJj" if "base64 <" in text else b"hi"
                self._chunks.append(
                    b"\n__AB_START_" + token.encode() + b"__\n"
                    + output
                    + b"\n\n__AB_EXIT_" + token.encode() + b"__" + str(code).encode() + b"\n"
                )
        elif "bash" in text:
            self._chunks.append(b"$ ")
        elif text.strip() == "ls":
            self._chunks.append(b"file.txt\n")

    def close(self) -> None:
        self.closed = True


class _FakeTransport:
    def __init__(self) -> None:
        self.opened: list[tuple] = []

    def open_channel(self, kind, dest, src, timeout=None):
        self.opened.append((kind, dest, src, timeout))
        return _FakeChannel([b"jump-ok\n"])


class _FakeClient:
    instances: list[_FakeClient] = []

    def __init__(self) -> None:
        self.closed = False
        self.connected = False
        self.channel = _FakeChannel([b"hi\n"])
        self.transport = _FakeTransport()
        _FakeClient.instances.append(self)

    def set_missing_host_key_policy(self, policy):
        self.policy = policy

    def connect(self, **kwargs):
        self.connected = True
        self.connect_kwargs = kwargs

    def get_transport(self):
        return self.transport

    def invoke_shell(self, width=80, height=24):
        self.shell = _FakeShell()
        return self.shell

    def exec_command(self, command, timeout=None, get_pty=False):
        self.last_command = command
        self.last_get_pty = get_pty
        stdin = _FakeStream(self.channel)
        return stdin, _FakeStream(self.channel), _FakeStream(self.channel)

    def close(self):
        self.closed = True


def _install_fake_paramiko(monkeypatch):
    fake = types.ModuleType("paramiko")
    _FakeClient.instances = []
    fake.SSHClient = _FakeClient
    fake.AutoAddPolicy = lambda: None
    monkeypatch.setitem(sys.modules, "paramiko", fake)
    return fake


def _install_fake_socks(monkeypatch):
    fake = types.ModuleType("socks")
    fake.SOCKS5 = 2
    calls: list[tuple] = []

    def create_connection(address, **kwargs):
        calls.append((address, kwargs))
        return "fake-socks-socket"

    fake.create_connection = create_connection
    fake.calls = calls
    monkeypatch.setitem(sys.modules, "socks", fake)
    return fake


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
    assert out.values[4] is True
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


def test_ssh_exec_strips_ansi(monkeypatch):
    _install_fake_paramiko(monkeypatch)
    reg = PluginRegistry()
    reg.register(SSHPlugin())
    session = reg.call("ssh.create_session", {"host": "h"})
    session.value.client.channel = _FakeChannel([b"\x1b[31mhi\x1b[0m\n"])
    result = reg.call("ssh.ssh_exec", {"session": session.value, "command": "ls"})
    assert result.ok
    assert result.values[0] == "hi\n"


def test_ssh_noninteractive_nonzero_exit_is_failure(monkeypatch):
    _install_fake_paramiko(monkeypatch)
    reg = PluginRegistry()
    reg.register(SSHPlugin())
    session = reg.call("ssh.create_session", {"host": "h"})
    session.value.client.channel = _FakeChannel([b"bad\n"], exit_code=2)
    result = reg.call("ssh.ssh_exec", {"session": session.value, "command": "false"})
    assert not result.ok
    assert result.detail["exit_code"] == 2
    assert result.detail["stdout"] == "bad\n"


def test_ssh_noninteractive_timeout_is_failure(monkeypatch):
    _install_fake_paramiko(monkeypatch)
    reg = PluginRegistry()
    reg.register(SSHPlugin())
    session = reg.call("ssh.create_session", {"host": "h"})
    session.value.client.channel = _FakeChannel([], exit_ready=False)
    result = reg.call(
        "ssh.ssh_exec",
        {"session": session.value, "command": "sleep 99", "timeout": 0.01},
    )
    assert not result.ok
    assert result.detail["timed_out"] is True


def test_ssh_socks5_proxy_for_target(monkeypatch):
    _install_fake_paramiko(monkeypatch)
    fake_socks = _install_fake_socks(monkeypatch)
    reg = PluginRegistry()
    reg.register(SSHPlugin())
    session = reg.call(
        "ssh.create_session",
        {
            "host": "target",
            "proxy": {"host": "proxy.local", "port": 1080, "user": "u", "pwd": "p"},
        },
    )
    assert session.ok
    assert fake_socks.calls[0][0] == ("target", 22)
    assert session.value.client.connect_kwargs["sock"] == "fake-socks-socket"


def test_ssh_jump_host_uses_shell_ssh(monkeypatch):
    _install_fake_paramiko(monkeypatch)
    fake_socks = _install_fake_socks(monkeypatch)
    reg = PluginRegistry()
    reg.register(SSHPlugin())
    session = reg.call(
        "ssh.create_session",
        {
            "host": "target",
            "port": 2222,
            "user": "deploy",
            "pwd": "target-pwd",
            "proxy": {"host": "proxy.local", "port": 1080},
            "jump": {"host": "jump", "port": 2222, "user": "ops"},
        },
    )
    assert session.ok
    jump_client = _FakeClient.instances[0]
    assert jump_client.connect_kwargs["hostname"] == "jump"
    assert jump_client.connect_kwargs["sock"] == "fake-socks-socket"
    assert fake_socks.calls[0][0] == ("jump", 2222)
    assert jump_client.transport.opened == []  # 不再使用 direct-tcpip
    assert jump_client.shell.sent[0].startswith("ssh -tt ")
    assert "deploy@target" in jump_client.shell.sent[0]
    assert "-p 2222" in jump_client.shell.sent[0]
    assert any("target-pwd" in item for item in jump_client.shell.sent)

    out = reg.call("ssh.ssh_exec", {"session": session.value, "command": "echo hi"})
    assert out.ok
    assert out.values[0] == "hi"
    assert out.values[2] == 0

    failed = reg.call("ssh.ssh_exec", {"session": session.value, "command": "false"})
    assert not failed.ok
    assert failed.detail["exit_code"] == 2

    started = reg.call(
        "ssh.ssh_exec",
        {
            "session": session.value,
            "command": "bash",
            "interactive": True,
            "idle_timeout": 0.01,
        },
    )
    assert started.ok
    assert started.values[3] == "jump-shell"
    sent = reg.call(
        "ssh.ssh_send",
        {"session": session.value, "channel_id": "jump-shell", "data": "ls"},
    )
    assert sent.ok
    read = reg.call(
        "ssh.ssh_read",
        {"session": session.value, "channel_id": "jump-shell", "idle_timeout": 0.01},
    )
    assert read.ok
    assert "file.txt" in read.values[0]


def test_ssh_interactive_stream_send_read(monkeypatch):
    _install_fake_paramiko(monkeypatch)
    reg = PluginRegistry()
    reg.register(SSHPlugin())
    session = reg.call("ssh.create_session", {"host": "h"})
    channel = session.value.client.channel
    channel._chunks = [b"user@host:~$ "]
    channel._exit_ready = False

    started = reg.call(
        "ssh.ssh_exec",
        {"session": session.value, "command": "bash", "interactive": True, "idle_timeout": 0.01},
    )
    assert started.ok
    assert started.values[0] == "user@host:~$ "
    channel_id = started.values[3]
    assert channel_id
    assert started.values[4] is False
    assert session.value.client.last_get_pty is True

    sent = reg.call(
        "ssh.ssh_send",
        {"session": session.value, "channel_id": channel_id, "data": "ls"},
    )
    assert sent.ok
    assert channel.sent[-1] == b"ls\n"

    channel._chunks = [b"file.txt\n"]
    channel._exit_ready = True
    read = reg.call(
        "ssh.ssh_read",
        {"session": session.value, "channel_id": channel_id, "idle_timeout": 0.01},
    )
    assert read.ok
    assert read.values[0] == "file.txt\n"
    assert read.values[3] is True


def test_ssh_jump_file_upload_download_with_file_platform(monkeypatch):
    _install_fake_paramiko(monkeypatch)
    reg = PluginRegistry()
    reg.register(SSHPlugin())
    session = reg.call(
        "ssh.create_session",
        {
            "host": "target",
            "pwd": "target-pwd",
            "jump": {"host": "jump"},
        },
    )
    assert session.ok
    from autobranch.plugins.file import store

    monkeypatch.setattr(
        store, "read_platform_file", lambda path: ("a.txt", b"abc")
    )
    written: dict = {}

    def fake_write(path, content, content_type="application/octet-stream", **kwargs):
        written.update({"path": path, "content": content})
        return {"path": path}

    monkeypatch.setattr(store, "write_platform_file", fake_write)
    uploaded = reg.call(
        "ssh.upload_file",
        {
            "session": session.value,
            "file_path": "input/a.txt",
            "remote_path": "/tmp/",
        },
    )
    assert uploaded.ok
    assert uploaded.values == (3, "/tmp/a.txt")

    downloaded = reg.call(
        "ssh.download_file",
        {"session": session.value, "remote_path": "/tmp/b.txt", "file_path": ""},
    )
    assert downloaded.ok
    assert written["path"] == "b.txt"
    assert written["content"] == b"abc"


def test_ssh_functions_declare_save_to():
    reg = PluginRegistry()
    reg.register(SSHPlugin())
    create = reg.function("ssh.create_session")
    assert create.output_param == "save_to"
    assert create.returns == {"session": "object"}
    exec_spec = reg.function("ssh.ssh_exec")
    assert exec_spec.output_param == "save_to"
    assert exec_spec.returns == {
        "stdout": "str",
        "stderr": "str",
        "exit_code": "int",
        "channel_id": "str",
        "exited": "bool",
    }
