"""SSH 插件：直连 / SOCKS5 / 跳板机、非交互执行与交互式流式会话。

设计要点：
- 非交互命令（默认）读取 stdout/stderr 直到 SSH 通道返回 exit-status，
  因此可以可靠判断“执行完成 + 退出码”。
- 交互命令（``interactive=True``）使用 PTY，等待 idle_timeout 后返回当前输出
  与 ``channel_id``；后续用 ``ssh_send`` / ``ssh_read`` / ``ssh_close_channel``
  像终端一样持续交互。
- 跳板机：先连接 jump 主机（可经 SOCKS5），在 jump 上打开 PTY shell 并执行
  ``ssh`` 命令登录目标机；不在 jump 上使用 ``direct-tcpip``（部分环境禁用）。
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import posixpath
import re
import shlex
import stat
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from autobranch.plugin_system import (
    FunctionResult,
    PluginBase,
    custom_type_param,
    engine_function,
)

_ANSI_RE = re.compile(
    r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))"
)
_PROMPT_LINE_RE = re.compile(
    r"^(?:\[[^\]]+\][#$>]|[^\s@]+@[^\s]+[:~][^\s]*[#$>])\s*$"
)


def strip_ansi(text: str) -> str:
    """移除常见 ANSI CSI/OSC 转义序列（终端颜色/控制码）。"""
    return _ANSI_RE.sub("", text)


def strip_shell_prompt(text: str) -> str:
    """移除 jump shell 输出末尾常见的交互提示符行。"""
    lines = strip_ansi(text).splitlines()
    while lines and _PROMPT_LINE_RE.match(lines[-1].strip()):
        lines.pop()
    return "\n".join(lines)


def _params(required: tuple[str, ...], **props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(required)}


@dataclass
class _ChannelState:
    """交互式命令的通道状态。"""

    channel: Any
    stdin: Any
    stdout: Any
    stderr: Any


@dataclass
class SSHConnection:
    """远程 SSH 会话对象（自定义类型 ``ssh_session`` 的值）。"""

    id: str
    client: Any | None = field(default=None, repr=False)
    jump_client: Any | None = field(default=None, repr=False)
    jump_shell: Any | None = field(default=None, repr=False)
    jump_buffer: str = field(default="", repr=False)
    channels: dict[str, _ChannelState] = field(default_factory=dict, repr=False)
    ref_count: int = 1
    pool_key: str = ""
    last_used_at: float = field(default_factory=time.monotonic)
    lock: Any = field(default_factory=threading.RLock, repr=False)

    def __str__(self) -> str:
        return f"SSHConnection(id={self.id[:8]}…)"

    def __repr__(self) -> str:
        return str(self)


class SSHPlugin(PluginBase):
    """SSH 能力：直连/代理/跳板会话、非交互命令、交互式流式命令。"""

    name = "ssh"
    description = (
        "SSH 远程能力：直连/SOCKS5/跳板机会话；非交互命令返回退出码；"
        "交互命令返回流式通道（send/read/close）"
    )

    @property
    def custom_types(self) -> dict[str, type]:
        return {"ssh_session": SSHConnection}

    def __init__(self) -> None:
        self._connections: dict[str, SSHConnection] = {}
        self._pool: dict[str, SSHConnection] = {}
        self._pool_lock = threading.RLock()

    def init(self, runtime: Any = None) -> None:
        pass

    def release(self) -> None:
        with self._pool_lock:
            connections = list({conn.id: conn for conn in self._connections.values()}.values())
            self._connections.clear()
            self._pool.clear()
        for conn in connections:
            self._close_connection(conn)

    # ------------------------------------------------------------- 会话

    @staticmethod
    def _secret_fingerprint(value: str | None) -> str:
        """认证材料只存摘要，避免池 key 中长期保留明文密码。"""
        if not value:
            return ""
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @classmethod
    def _proxy_key(cls, proxy: dict | None) -> dict:
        if not isinstance(proxy, dict):
            return {}
        return {
            "type": proxy.get("type", "socks5"),
            "host": str(proxy.get("host") or ""),
            "port": int(proxy.get("port") or 0),
            "user": str(proxy.get("user") or ""),
            "pwd": cls._secret_fingerprint(proxy.get("pwd")),
        }

    @classmethod
    def _jump_key(cls, jump: dict | None, fallback_proxy: dict | None = None) -> dict:
        if not isinstance(jump, dict):
            return {}
        jump_proxy = jump.get("proxy") or fallback_proxy
        return {
            "host": str(jump.get("host") or "").strip(),
            "port": int(jump.get("port") or 22),
            "user": str(jump.get("user") or "root"),
            "pwd": cls._secret_fingerprint(jump.get("pwd")),
            "key": cls._secret_fingerprint(jump.get("key")),
            "proxy": cls._proxy_key(jump_proxy),
        }

    @classmethod
    def _session_key(
        cls,
        host: str,
        port: int,
        user: str,
        *,
        pwd: str | None = None,
        key: str | None = None,
        proxy: dict | None = None,
        jump: dict | None = None,
    ) -> str:
        identity = {
            "host": str(host or "").strip(),
            "port": int(port),
            "user": str(user or "root"),
            "pwd": cls._secret_fingerprint(pwd),
            "key": cls._secret_fingerprint(key),
            "proxy": cls._proxy_key(proxy),
            "jump": cls._jump_key(jump, proxy),
        }
        return hashlib.sha256(
            json.dumps(identity, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _is_alive(conn: SSHConnection) -> bool:
        try:
            if conn.jump_shell is not None:
                if getattr(conn.jump_shell, "closed", False):
                    return False
                client = conn.jump_client
            else:
                client = conn.client
            if client is None:
                return False
            transport = client.get_transport()
            if transport is None:
                return False
            checker = getattr(transport, "is_active", None)
            return bool(checker()) if callable(checker) else True
        except Exception:  # noqa: BLE001
            return False

    def _cleanup_idle(self, max_idle: float = 300.0) -> None:
        """清理引用计数为 0 且空闲超时的池会话（无后台线程）。"""
        now = time.monotonic()
        expired: list[SSHConnection] = []
        with self._pool_lock:
            for key, conn in list(self._pool.items()):
                if conn.ref_count <= 0 and now - conn.last_used_at > max_idle:
                    self._pool.pop(key, None)
                    self._connections.pop(conn.id, None)
                    expired.append(conn)
        for conn in expired:
            self._close_connection(conn)

    def _cached_session(self, key: str) -> SSHConnection | None:
        expired: SSHConnection | None = None
        with self._pool_lock:
            conn = self._pool.get(key)
            if conn is None:
                return None
            if self._is_alive(conn):
                conn.ref_count += 1
                conn.last_used_at = time.monotonic()
                return conn
            self._pool.pop(key, None)
            self._connections.pop(conn.id, None)
            expired = conn
        if expired is not None:
            self._close_connection(expired)
        return None

    def _register_session(self, conn: SSHConnection, key: str) -> SSHConnection:
        duplicate: SSHConnection | None = None
        result = conn
        with self._pool_lock:
            existing = self._pool.get(key)
            if existing is not None and self._is_alive(existing):
                existing.ref_count += 1
                existing.last_used_at = time.monotonic()
                duplicate = conn
                result = existing
            else:
                if existing is not None:
                    self._pool.pop(key, None)
                    self._connections.pop(existing.id, None)
                    duplicate = existing
                conn.pool_key = key
                conn.ref_count = 1
                conn.last_used_at = time.monotonic()
                self._pool[key] = conn
                self._connections[conn.id] = conn
        if duplicate is not None:
            self._close_connection(duplicate)
        return result

    @engine_function(
        name="create_session",
        description=(
            "创建远程 SSH 会话。支持密码/私钥、SOCKS5 代理、SSH 跳板机；"
            "有 jump 时 proxy 用于连接跳板机，jump 到目标机通过在 jump 上执行 ssh 命令跳转"
        ),
        parameters=_params(
            ("host",),
            host={"type": "string", "description": "目标主机 IP / 域名"},
            port={"type": "integer", "description": "SSH 端口（默认 22）"},
            user={"type": "string", "description": "登录用户名"},
            pwd={
                "type": "string",
                "description": "目标密码（jump 模式必需；直连时与 key 二选一）",
            },
            key={"type": "string", "description": "私钥文件路径（与 pwd 二选一）"},
            timeout={"type": "number", "description": "连接超时秒数（默认 15）"},
            proxy={
                "type": "object",
                "description": "SOCKS5 代理：{host, port, user?, pwd?}",
                "properties": {
                    "type": {"type": "string", "enum": ["socks5"]},
                    "host": {"type": "string"},
                    "port": {"type": "integer"},
                    "user": {"type": "string"},
                    "pwd": {"type": "string"},
                },
            },
            jump={
                "type": "object",
                "description": (
                    "跳板机：{host, port?, user?, pwd?, key?, timeout?, proxy?}；"
                    "jump.proxy 为连接跳板机的 SOCKS5 代理"
                ),
                "properties": {
                    "host": {"type": "string"},
                    "port": {"type": "integer"},
                    "user": {"type": "string"},
                    "pwd": {"type": "string"},
                    "key": {"type": "string"},
                    "timeout": {"type": "number"},
                    "proxy": {"type": "object"},
                },
            },
        ),
        returns={"session": "ssh_session"},
        output_param="save_to",
    )
    def create_session(
        self,
        host: str,
        port: int = 22,
        user: str = "root",
        pwd: str | None = None,
        key: str | None = None,
        timeout: float = 15.0,
        proxy: dict | None = None,
        jump: dict | None = None,
    ) -> FunctionResult:
        pool_key = self._session_key(
            host, port, user, pwd=pwd, key=key, proxy=proxy, jump=jump
        )
        self._cleanup_idle()
        cached = self._cached_session(pool_key)
        if cached is not None:
            return FunctionResult.success(cached)
        try:
            import paramiko
        except ImportError:
            return FunctionResult.failure(
                "paramiko 未安装（ssh 插件依赖，请联系环境安装）", code="SSH_ERROR"
            )

        jump_client = None
        jump_shell = None
        client = None
        try:
            if jump:
                jump_host = str(jump.get("host") or "").strip()
                if not jump_host:
                    return FunctionResult.failure("jump.host 不能为空", code="SSH_ERROR")
                jump_proxy = jump.get("proxy") or proxy
                jump_client = self._connect_client(
                    paramiko,
                    host=jump_host,
                    port=int(jump.get("port") or 22),
                    user=str(jump.get("user") or "root"),
                    pwd=jump.get("pwd"),
                    key=jump.get("key"),
                    timeout=float(jump.get("timeout") or timeout),
                    proxy=jump_proxy,
                )
                if not pwd:
                    raise RuntimeError("跳板机跳转模式目标认证需要 pwd（密码）")
                jump_shell = self._open_jump_shell(
                    jump_client,
                    host=host,
                    port=int(port),
                    user=user,
                    pwd=pwd,
                    timeout=timeout,
                )
            else:
                client = self._connect_client(
                    paramiko,
                    host=host,
                    port=int(port),
                    user=user,
                    pwd=pwd,
                    key=key,
                    timeout=timeout,
                    proxy=proxy,
                )
        except Exception as exc:  # noqa: BLE001
            self._safe_close(jump_shell)
            self._safe_close(jump_client)
            self._safe_close(client)
            return FunctionResult.failure(f"SSH 连接失败: {exc}", code="SSH_ERROR")

        conn = SSHConnection(
            id=uuid.uuid4().hex,
            client=client,
            jump_client=jump_client,
            jump_shell=jump_shell,
            pool_key=pool_key,
        )
        return FunctionResult.success(self._register_session(conn, pool_key))

    @engine_function(
        name="close_session",
        description="关闭远程 SSH 会话（同时关闭跳板机连接与交互通道）",
        parameters=_params(
            ("session",),
            session=custom_type_param(
                "ssh_session", "SSH 会话对象，使用 Param.变量名 引用"
            ),
        ),
    )
    def close_session(self, session: SSHConnection) -> FunctionResult:
        with self._pool_lock:
            conn = self._connections.get(session.id) if isinstance(session, SSHConnection) else None
            if conn is None:
                return FunctionResult.failure("会话不存在或已关闭", code="SSH_ERROR")
            conn.ref_count -= 1
            if conn.ref_count > 0:
                conn.last_used_at = time.monotonic()
                return FunctionResult.success()
            self._connections.pop(conn.id, None)
            if conn.pool_key:
                self._pool.pop(conn.pool_key, None)
        self._close_connection(conn)
        return FunctionResult.success()

    # ------------------------------------------------------------- 执行

    @engine_function(
        name="ssh_exec",
        description=(
            "执行命令。默认非交互模式：流式读取直到进程退出，返回 stdout/stderr/exit_code，"
            "非零退出码为失败；interactive=true 时使用 PTY，等待 idle_timeout 后返回当前输出"
            "与 channel_id，后续用 ssh_send/ssh_read 交互"
        ),
        parameters=_params(
            ("session", "command"),
            session=custom_type_param(
                "ssh_session", "SSH 会话对象，使用 Param.变量名 引用"
            ),
            command={"type": "string", "description": "要执行的命令"},
            timeout={"type": "number", "description": "非交互命令总超时（默认 30 秒）"},
            stdin={"type": "string", "description": "启动后立即写入的标准输入"},
            interactive={"type": "boolean", "description": "是否使用 PTY 交互模式"},
            idle_timeout={
                "type": "number",
                "description": "交互模式无输出多久后返回（默认 1 秒）",
            },
        ),
        returns={
            "stdout": "str",
            "stderr": "str",
            "exit_code": "int",
            "channel_id": "str",
            "exited": "bool",
        },
        output_param="save_to",
    )
    def ssh_exec(
        self,
        session: SSHConnection,
        command: str,
        timeout: float = 30.0,
        stdin: str | None = None,
        interactive: bool = False,
        idle_timeout: float = 1.0,
    ) -> FunctionResult:
        conn = self._find(session)
        if conn is None:
            return FunctionResult.failure("会话不存在或已关闭", code="SSH_ERROR")
        if conn.jump_shell is not None:
            if interactive:
                payload = f"{command}\n"
                if stdin:
                    payload += stdin + ("\n" if not stdin.endswith("\n") else "")
                try:
                    with conn.lock:
                        conn.jump_shell.sendall(payload)
                        out = self._read_shell_idle_locked(conn, idle_timeout)
                except Exception as exc:  # noqa: BLE001
                    return FunctionResult.failure(
                        f"跳板机 shell 命令执行失败: {exc}", code="SSH_ERROR"
                    )
                return FunctionResult.success(out, "", 0, "jump-shell", False)
            return self._exec_shell(conn, command, timeout)
        try:
            stdin_stream, stdout, stderr = conn.client.exec_command(
                command,
                timeout=timeout,
                get_pty=bool(interactive),
            )
            channel = stdout.channel
            if stdin:
                self._write(stdin_stream, channel, stdin, newline=False)
        except Exception as exc:  # noqa: BLE001
            return FunctionResult.failure(f"命令执行失败: {exc}", code="SSH_ERROR")

        if interactive:
            out, err, code, exited, timed_out = self._read_channel(
                channel, timeout=idle_timeout, require_exit=False
            )
            if timed_out:
                return FunctionResult.failure(
                    "交互命令读取超时",
                    code="SSH_ERROR",
                    stdout=out,
                    stderr=err,
                    exit_code=code,
                )
            result = FunctionResult.success(out, err, code, "", exited)
            if not exited:
                channel_id = uuid.uuid4().hex
                conn.channels[channel_id] = _ChannelState(
                    channel=channel,
                    stdin=stdin_stream,
                    stdout=stdout,
                    stderr=stderr,
                )
                result.values = (out, err, code, channel_id, False)
            else:
                self._safe_close(channel)
            return result

        out, err, code, exited, timed_out = self._read_channel(
            channel, timeout=timeout, require_exit=True
        )
        self._safe_close(channel)
        if timed_out or not exited:
            return FunctionResult.failure(
                f"命令执行超时（{timeout} 秒）",
                code="SSH_ERROR",
                stdout=out,
                stderr=err,
                exit_code=code,
                timed_out=True,
            )
        if code != 0:
            return FunctionResult.failure(
                f"命令退出码 {code}: {err}",
                code="SSH_ERROR",
                stdout=out,
                stderr=err,
                exit_code=code,
            )
        return FunctionResult.success(out, err, code, "", True)

    @engine_function(
        name="ssh_send",
        description="向交互式命令通道写入标准输入（newline=true 自动追加换行）",
        parameters=_params(
            ("session", "channel_id", "data"),
            session=custom_type_param("ssh_session", "SSH 会话对象"),
            channel_id={
                "type": "string",
                "description": "ssh_exec(interactive=true) 返回的通道 ID",
            },
            data={"type": "string", "description": "要写入的文本"},
            newline={"type": "boolean", "description": "是否追加换行（默认 true）"},
        ),
    )
    def ssh_send(
        self,
        session: SSHConnection,
        channel_id: str,
        data: str,
        newline: bool = True,
    ) -> FunctionResult:
        conn = self._find(session)
        if conn is not None and conn.jump_shell is not None and channel_id in (
            "jump-shell",
            "",
        ):
            try:
                with conn.lock:
                    conn.jump_shell.sendall(str(data) + ("\n" if newline else ""))
            except Exception as exc:  # noqa: BLE001
                return FunctionResult.failure(
                    f"写入跳板机 shell 失败: {exc}", code="SSH_ERROR"
                )
            return FunctionResult.success()
        state = conn.channels.get(channel_id) if conn is not None else None
        if conn is None or state is None:
            return FunctionResult.failure("交互通道不存在或已关闭", code="SSH_ERROR")
        try:
            self._write(state.stdin, state.channel, data, newline=newline)
        except Exception as exc:  # noqa: BLE001
            return FunctionResult.failure(f"写入交互通道失败: {exc}", code="SSH_ERROR")
        return FunctionResult.success()

    @engine_function(
        name="ssh_read",
        description=(
            "读取交互式命令通道的新输出（无输出 idle_timeout 秒后返回）；"
            "返回 stdout/stderr/exit_code/exited"
        ),
        parameters=_params(
            ("session", "channel_id"),
            session=custom_type_param("ssh_session", "SSH 会话对象"),
            channel_id={"type": "string", "description": "交互通道 ID"},
            idle_timeout={"type": "number", "description": "无输出等待秒数（默认 1）"},
        ),
        returns={
            "stdout": "str",
            "stderr": "str",
            "exit_code": "int",
            "exited": "bool",
        },
    )
    def ssh_read(
        self,
        session: SSHConnection,
        channel_id: str,
        idle_timeout: float = 1.0,
    ) -> FunctionResult:
        conn = self._find(session)
        if conn is not None and conn.jump_shell is not None and channel_id in (
            "jump-shell",
            "",
        ):
            try:
                out = self._read_shell_idle(conn, idle_timeout)
            except Exception as exc:  # noqa: BLE001
                return FunctionResult.failure(
                    f"读取跳板机 shell 失败: {exc}", code="SSH_ERROR"
                )
            return FunctionResult.success(out, "", 0, False)
        state = conn.channels.get(channel_id) if conn is not None else None
        if conn is None or state is None:
            return FunctionResult.failure("交互通道不存在或已关闭", code="SSH_ERROR")
        out, err, code, exited, timed_out = self._read_channel(
            state.channel, timeout=idle_timeout, require_exit=False
        )
        if timed_out:
            return FunctionResult.failure(
                "读取交互通道超时",
                code="SSH_ERROR",
                stdout=out,
                stderr=err,
                exit_code=code,
            )
        if exited:
            self._safe_close(state.channel)
            conn.channels.pop(channel_id, None)
        return FunctionResult.success(out, err, code, exited)

    @engine_function(
        name="ssh_close_channel",
        description="关闭交互式命令通道（不关闭 SSH 会话）",
        parameters=_params(
            ("session", "channel_id"),
            session=custom_type_param("ssh_session", "SSH 会话对象"),
            channel_id={"type": "string", "description": "交互通道 ID"},
        ),
    )
    def ssh_close_channel(self, session: SSHConnection, channel_id: str) -> FunctionResult:
        conn = self._find(session)
        if conn is not None and conn.jump_shell is not None and channel_id in (
            "jump-shell",
            "",
        ):
            with conn.lock:
                self._safe_close(conn.jump_shell)
                conn.jump_shell = None
                conn.jump_buffer = ""
            return FunctionResult.success()
        state = conn.channels.pop(channel_id, None) if conn is not None else None
        if conn is None or state is None:
            return FunctionResult.failure("交互通道不存在或已关闭", code="SSH_ERROR")
        self._safe_close(state.channel)
        return FunctionResult.success()

    # ------------------------------------------------------------- 文件传输

    @engine_function(
        name="upload_file",
        description=(
            "从文件管理平台读取文件并上传到远程主机路径；jump 模式通过目标 shell "
            "的 base64 写入，直连模式使用 SFTP"
        ),
        parameters=_params(
            ("session", "file_path", "remote_path"),
            session=custom_type_param("ssh_session", "SSH 会话对象"),
            file_path={"type": "string", "description": "文件管理平台中的文件路径"},
            remote_path={
                "type": "string",
                "description": "远程目标文件路径（以 / 结尾时自动使用平台文件名）",
            },
            timeout={"type": "number", "description": "传输超时秒数（默认 60）"},
        ),
        returns={"size": "int", "path": "str"},
    )
    def upload_file(
        self,
        session: SSHConnection,
        file_path: str,
        remote_path: str,
        timeout: float = 60.0,
    ) -> FunctionResult:
        conn = self._find(session)
        if conn is None:
            return FunctionResult.failure("会话不存在或已关闭", code="SSH_ERROR")
        try:
            from autobranch.plugins.file.store import read_platform_file

            filename, content = read_platform_file(file_path)
        except Exception as exc:  # noqa: BLE001
            return FunctionResult.failure(f"读取文件管理平台文件失败: {exc}", code="SSH_ERROR")
        target = str(remote_path or "")
        if not target or target.endswith("/"):
            target = posixpath.join(target or ".", filename)
        try:
            if conn.jump_shell is not None:
                self._upload_jump_shell(conn, target, content, timeout)
            else:
                self._upload_sftp(conn, target, content, timeout)
        except Exception as exc:  # noqa: BLE001
            return FunctionResult.failure(f"上传失败: {exc}", code="SSH_ERROR")
        return FunctionResult.success(len(content), target)

    @engine_function(
        name="download_file",
        description=(
            "从远程主机下载文件并保存到文件管理平台；jump 模式通过目标 shell "
            "的 base64 读取，直连模式使用 SFTP"
        ),
        parameters=_params(
            ("session", "remote_path"),
            session=custom_type_param("ssh_session", "SSH 会话对象"),
            remote_path={"type": "string", "description": "远程文件路径"},
            file_path={
                "type": "string",
                "description": "文件管理平台目标路径（空/以 / 结尾时使用远程文件名）",
            },
            timeout={"type": "number", "description": "传输超时秒数（默认 60）"},
        ),
        returns={"size": "int", "path": "str"},
    )
    def download_file(
        self,
        session: SSHConnection,
        remote_path: str,
        file_path: str = "",
        timeout: float = 60.0,
    ) -> FunctionResult:
        conn = self._find(session)
        if conn is None:
            return FunctionResult.failure("会话不存在或已关闭", code="SSH_ERROR")
        try:
            if conn.jump_shell is not None:
                content = self._download_jump_shell(conn, remote_path, timeout)
            else:
                content = self._download_sftp(conn, remote_path)
        except Exception as exc:  # noqa: BLE001
            return FunctionResult.failure(f"下载失败: {exc}", code="SSH_ERROR")
        try:
            from autobranch.plugins.file.store import (
                resolve_download_path,
                write_platform_file,
            )

            target = resolve_download_path(remote_path, file_path)
            record = write_platform_file(target, content, filename=posixpath.basename(remote_path))
        except Exception as exc:  # noqa: BLE001
            return FunctionResult.failure(f"写入文件管理平台失败: {exc}", code="SSH_ERROR")
        return FunctionResult.success(len(content), record["path"])

    @engine_function(
        name="upload_dir",
        description=(
            "从文件管理平台递归上传目录到远程目录；直连使用 SFTP，"
            "跳板 shell 使用 base64 逐文件写入"
        ),
        parameters=_params(
            ("session", "dir_path", "remote_dir"),
            session=custom_type_param("ssh_session", "SSH 会话对象"),
            dir_path={"type": "string", "description": "文件管理平台目录路径"},
            remote_dir={"type": "string", "description": "远程目标目录"},
            timeout={"type": "number", "description": "单文件传输超时秒数（默认 60）"},
        ),
        returns={"files": "int", "path": "str"},
    )
    def upload_dir(
        self,
        session: SSHConnection,
        dir_path: str,
        remote_dir: str,
        timeout: float = 60.0,
    ) -> FunctionResult:
        conn = self._find(session)
        if conn is None:
            return FunctionResult.failure("会话不存在或已关闭", code="SSH_ERROR")
        try:
            from autobranch.plugins.file.service import normalize_path
            from autobranch.plugins.file.store import (
                get_platform_directory,
                list_platform_files,
                read_platform_file,
            )

            source = normalize_path(dir_path)
            if source and get_platform_directory(source) is None:
                return FunctionResult.failure(f"平台目录不存在: {source}", code="SSH_ERROR")
            files = list_platform_files(source)
            target_dir = str(remote_dir or "").strip()
            if not target_dir:
                return FunctionResult.failure("remote_dir 不能为空", code="SSH_ERROR")
            if conn.jump_shell is not None:
                if not files:
                    result = self._exec_shell(
                        conn, f"mkdir -p {shlex.quote(target_dir)}", timeout
                    )
                    if not result.ok:
                        return FunctionResult.failure(
                            result.error or "创建远程目录失败", code="SSH_ERROR"
                        )
                for item in files:
                    _filename, content = read_platform_file(item["path"])
                    remote_path = posixpath.join(target_dir, item["relative"])
                    self._upload_jump_shell(conn, remote_path, content, timeout)
            else:
                self._upload_dir_sftp(
                    conn,
                    target_dir,
                    [(item["relative"], item["path"]) for item in files],
                    timeout,
                )
        except Exception as exc:  # noqa: BLE001
            return FunctionResult.failure(f"上传目录失败: {exc}", code="SSH_ERROR")
        return FunctionResult.success(len(files), target_dir)

    @engine_function(
        name="download_dir",
        description=(
            "从远程目录递归下载到文件管理平台；直连使用 SFTP，"
            "跳板 shell 使用 find + base64"
        ),
        parameters=_params(
            ("session", "remote_dir"),
            session=custom_type_param("ssh_session", "SSH 会话对象"),
            remote_dir={"type": "string", "description": "远程目录路径"},
            dir_path={
                "type": "string",
                "description": "文件管理平台目标目录（空/以 / 结尾时使用远程目录名）",
            },
            timeout={"type": "number", "description": "单文件传输超时秒数（默认 60）"},
        ),
        returns={"files": "int", "path": "str"},
    )
    def download_dir(
        self,
        session: SSHConnection,
        remote_dir: str,
        dir_path: str = "",
        timeout: float = 60.0,
    ) -> FunctionResult:
        conn = self._find(session)
        if conn is None:
            return FunctionResult.failure("会话不存在或已关闭", code="SSH_ERROR")
        source = str(remote_dir or "").strip().rstrip("/")
        if not source:
            return FunctionResult.failure("remote_dir 不能为空", code="SSH_ERROR")
        try:
            from autobranch.plugins.file.service import path_join, path_name
            from autobranch.plugins.file.store import (
                ensure_platform_directory,
                write_platform_file,
            )

            target_dir = str(dir_path or "").replace("\\", "/")
            if not target_dir or target_dir.endswith("/"):
                target_dir = path_join(target_dir, path_name(source))
            ensure_platform_directory(target_dir)
            if conn.jump_shell is not None:
                count = self._download_dir_jump_shell(
                    conn, source, target_dir, timeout, write_platform_file
                )
            else:
                count = self._download_dir_sftp(
                    conn, source, target_dir, write_platform_file
                )
        except Exception as exc:  # noqa: BLE001
            return FunctionResult.failure(f"下载目录失败: {exc}", code="SSH_ERROR")
        return FunctionResult.success(count, target_dir)

    @staticmethod
    def _upload_dir_sftp(
        conn: SSHConnection,
        remote_dir: str,
        entries: list[tuple[str, str]],
        timeout: float,
    ) -> None:
        if conn.client is None:
            raise RuntimeError("目标 SSH 客户端不可用")
        sftp = conn.client.open_sftp()
        try:
            SSHPlugin._sftp_ensure_dir(sftp, remote_dir)
            for relative, platform_path in entries:
                from autobranch.plugins.file.store import read_platform_file

                _filename, content = read_platform_file(platform_path)
                remote_path = posixpath.join(remote_dir, relative)
                SSHPlugin._sftp_ensure_dir(sftp, posixpath.dirname(remote_path))
                sftp.putfo(io.BytesIO(content), remote_path)
        finally:
            sftp.close()

    @staticmethod
    def _download_dir_sftp(
        conn: SSHConnection,
        remote_dir: str,
        target_dir: str,
        write_platform_file: Any,
    ) -> int:
        if conn.client is None:
            raise RuntimeError("目标 SSH 客户端不可用")
        from autobranch.plugins.file.service import path_join

        sftp = conn.client.open_sftp()
        count = 0
        try:
            def walk(remote: str, relative: str) -> None:
                nonlocal count
                for attr in sftp.listdir_attr(remote):
                    child_remote = posixpath.join(remote, attr.filename)
                    child_relative = (
                        posixpath.join(relative, attr.filename)
                        if relative
                        else attr.filename
                    )
                    if stat.S_ISDIR(attr.st_mode):
                        walk(child_remote, child_relative)
                    else:
                        buffer = io.BytesIO()
                        sftp.getfo(child_remote, buffer)
                        write_platform_file(
                            path_join(target_dir, child_relative),
                            buffer.getvalue(),
                            filename=attr.filename,
                        )
                        count += 1

            walk(remote_dir, "")
        finally:
            sftp.close()
        return count

    @classmethod
    def _download_dir_jump_shell(
        cls,
        conn: SSHConnection,
        remote_dir: str,
        target_dir: str,
        timeout: float,
        write_platform_file: Any,
    ) -> int:
        from autobranch.plugins.file.service import path_join

        listing = cls._exec_shell(
            conn, f"find {shlex.quote(remote_dir)} -type f -print", timeout
        )
        if not listing.ok:
            raise RuntimeError(listing.error or "远程目录遍历失败")
        files = [line.strip() for line in listing.values[0].splitlines() if line.strip()]
        base = remote_dir.rstrip("/")
        count = 0
        for remote_path in files:
            relative = (
                remote_path[len(base) :].lstrip("/")
                if remote_path.startswith(base)
                else posixpath.basename(remote_path)
            )
            content = cls._download_jump_shell(conn, remote_path, timeout)
            write_platform_file(
                path_join(target_dir, relative),
                content,
                filename=posixpath.basename(remote_path),
            )
            count += 1
        return count

    @staticmethod
    def _sftp_ensure_dir(sftp: Any, path: str) -> None:
        if not path or path in (".", "/"):
            return
        current = "/" if path.startswith("/") else ""
        for part in path.strip("/").split("/"):
            if not part:
                continue
            current = posixpath.join(current, part) if current else part
            try:
                sftp.stat(current)
            except OSError:
                sftp.mkdir(current)

    @classmethod
    def _upload_jump_shell(
        cls, conn: SSHConnection, remote_path: str, content: bytes, timeout: float
    ) -> None:
        parent = posixpath.dirname(remote_path)
        encoded = base64.b64encode(content).decode("ascii")
        command = ""
        if parent:
            command += f"mkdir -p {shlex.quote(parent)} && "
        command += (
            f"base64 -d > {shlex.quote(remote_path)} <<'__AB_B64__'\n"
            f"{encoded}\n__AB_B64__"
        )
        result = cls._exec_shell(conn, command, timeout)
        if not result.ok:
            raise RuntimeError(result.error or "远程写入失败")

    @classmethod
    def _download_jump_shell(
        cls, conn: SSHConnection, remote_path: str, timeout: float
    ) -> bytes:
        result = cls._exec_shell(conn, f"base64 < {shlex.quote(remote_path)}", timeout)
        if not result.ok:
            raise RuntimeError(result.error or "远程读取失败")
        try:
            return base64.b64decode(result.values[0], validate=False)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"远程 base64 解码失败: {exc}") from exc

    @staticmethod
    def _upload_sftp(
        conn: SSHConnection, remote_path: str, content: bytes, timeout: float
    ) -> None:
        if conn.client is None:
            raise RuntimeError("目标 SSH 客户端不可用")
        parent = posixpath.dirname(remote_path)
        if parent:
            _stdin, stdout, _stderr = conn.client.exec_command(
                f"mkdir -p {shlex.quote(parent)}", timeout=timeout
            )
            code = stdout.channel.recv_exit_status()
            if code != 0:
                raise RuntimeError(f"创建远程目录失败（exit={code}）")
        sftp = conn.client.open_sftp()
        try:
            sftp.putfo(io.BytesIO(content), remote_path)
        finally:
            sftp.close()

    @staticmethod
    def _download_sftp(conn: SSHConnection, remote_path: str) -> bytes:
        if conn.client is None:
            raise RuntimeError("目标 SSH 客户端不可用")
        sftp = conn.client.open_sftp()
        try:
            buffer = io.BytesIO()
            sftp.getfo(remote_path, buffer)
            return buffer.getvalue()
        finally:
            sftp.close()

    # ------------------------------------------------------------- 内部

    @classmethod
    def _open_jump_shell(
        cls,
        jump_client: Any,
        *,
        host: str,
        port: int,
        user: str,
        pwd: str,
        timeout: float,
    ) -> Any:
        """在跳板机上打开 PTY shell，并用 ssh 命令登录目标机。

        部分跳板机禁止 ``direct-tcpip``，但允许在 shell 中执行 ssh；
        登录后关闭 shell echo，便于后续用唯一标记切分命令输出。
        """
        shell = jump_client.invoke_shell(width=200, height=50)
        try:
            cls._drain_shell(shell, 0.05)
            target = shlex.quote(f"{user}@{host}")
            command = (
                "ssh -tt -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
                f"-o ConnectTimeout={max(1, int(timeout))} -p {int(port)} {target}\n"
            )
            shell.sendall(command)
            buffer = ""
            password_sent = False
            start = time.monotonic()
            last_data = start
            while time.monotonic() - start < timeout:
                chunk = cls._pump_shell(shell)
                now = time.monotonic()
                if chunk:
                    buffer += chunk
                    last_data = now
                lowered = buffer.lower()
                if any(
                    marker in lowered
                    for marker in (
                        "permission denied",
                        "connection refused",
                        "no route to host",
                        "could not resolve",
                    )
                ):
                    raise RuntimeError(f"跳板机登录目标失败: {buffer[-300:]}")
                if not password_sent and (
                    "password:" in lowered or "password for" in lowered
                ):
                    shell.sendall(pwd + "\n")
                    password_sent = True
                    buffer = ""
                    last_data = now
                    continue
                if (
                    password_sent
                    and buffer.strip()
                    and re.search(r"[$#] ?$", buffer.strip())
                    and now - last_data > 0.2
                ):
                    break
                if password_sent and now - last_data > 1.0:
                    break
                if (
                    not password_sent
                    and buffer.strip()
                    and re.search(r"[$#] ?$", buffer.strip())
                    and now - last_data > 0.5
                ):
                    break
                time.sleep(0.03)
            else:
                raise RuntimeError("跳板机登录目标超时（未检测到目标 shell 提示符）")
            if "permission denied" in buffer.lower():
                raise RuntimeError(f"跳板机登录目标失败: {buffer[-300:]}")
            shell.sendall("stty -echo 2>/dev/null || true\n")
            time.sleep(0.1)
            cls._drain_shell(shell, 0.05)
            return shell
        except Exception:
            cls._safe_close(shell)
            raise

    @staticmethod
    def _pump_shell(channel: Any) -> str:
        parts: list[bytes] = []
        while channel.recv_ready():
            parts.append(channel.recv(65536))
        while channel.recv_stderr_ready():
            parts.append(channel.recv_stderr(65536))
        return b"".join(parts).decode("utf-8", "replace")

    @classmethod
    def _drain_shell(cls, channel: Any, idle_timeout: float) -> str:
        parts: list[str] = []
        last_data = time.monotonic()
        while time.monotonic() - last_data <= idle_timeout:
            chunk = cls._pump_shell(channel)
            if chunk:
                parts.append(chunk)
                last_data = time.monotonic()
            else:
                time.sleep(0.02)
        return "".join(parts)

    @classmethod
    def _exec_shell(
        cls, conn: SSHConnection, command: str, timeout: float
    ) -> FunctionResult:
        with conn.lock:
            return cls._exec_shell_locked(conn, command, timeout)

    @classmethod
    def _exec_shell_locked(
        cls, conn: SSHConnection, command: str, timeout: float
    ) -> FunctionResult:
        shell = conn.jump_shell
        if shell is None:
            return FunctionResult.failure("跳板机 shell 已关闭", code="SSH_ERROR")
        token = uuid.uuid4().hex
        start_marker = f"__AB_START_{token}__"
        end_marker = f"__AB_EXIT_{token}__"
        payload = (
            f"printf '\\n{start_marker}\\n'; {command}\n"
            f"printf '\\n{end_marker}%s\\n' \"$?\"\n"
        )
        try:
            conn.jump_buffer = ""
            shell.sendall(payload)
        except Exception as exc:  # noqa: BLE001
            return FunctionResult.failure(f"跳板机 shell 写入失败: {exc}", code="SSH_ERROR")
        start = time.monotonic()
        buffer = ""
        pattern = re.compile(re.escape(end_marker) + r"(\d+)")
        while time.monotonic() - start <= timeout:
            try:
                buffer += cls._pump_shell(shell)
            except Exception as exc:  # noqa: BLE001
                return FunctionResult.failure(f"跳板机 shell 读取失败: {exc}", code="SSH_ERROR")
            matches = list(pattern.finditer(buffer))
            if matches:
                match = matches[-1]
                start_index = buffer.rfind(start_marker, 0, match.start())
                if start_index < 0:
                    continue
                output = buffer[start_index + len(start_marker) : match.start()]
                output = strip_shell_prompt(output.lstrip("\r\n").rstrip("\r\n"))
                conn.jump_buffer = ""
                code = int(match.group(1))
                if code != 0:
                    return FunctionResult.failure(
                        f"命令退出码 {code}: {output[-500:]}",
                        code="SSH_ERROR",
                        stdout=output,
                        stderr="",
                        exit_code=code,
                    )
                return FunctionResult.success(output, "", code, "", True)
            time.sleep(0.03)
        conn.jump_buffer = buffer
        return FunctionResult.failure(
            f"命令执行超时（{timeout} 秒）",
            code="SSH_ERROR",
            stdout=strip_ansi(buffer),
            stderr="",
            exit_code=-1,
            timed_out=True,
        )

    @classmethod
    def _read_shell_idle(cls, conn: SSHConnection, idle_timeout: float) -> str:
        with conn.lock:
            return cls._read_shell_idle_locked(conn, idle_timeout)

    @classmethod
    def _read_shell_idle_locked(cls, conn: SSHConnection, idle_timeout: float) -> str:
        shell = conn.jump_shell
        if shell is None:
            raise RuntimeError("跳板机 shell 已关闭")
        parts = [conn.jump_buffer]
        conn.jump_buffer = ""
        last_data = time.monotonic()
        while time.monotonic() - last_data <= idle_timeout:
            chunk = cls._pump_shell(shell)
            if chunk:
                parts.append(chunk)
                last_data = time.monotonic()
            else:
                time.sleep(0.02)
        return "".join(parts)

    def _find(self, session: SSHConnection) -> SSHConnection | None:
        if not isinstance(session, SSHConnection):
            return None
        with self._pool_lock:
            conn = self._connections.get(session.id)
            if conn is not None:
                conn.last_used_at = time.monotonic()
            return conn

    @staticmethod
    def _connect_client(
        paramiko_module: Any,
        *,
        host: str,
        port: int,
        user: str,
        pwd: str | None,
        key: str | None,
        timeout: float,
        proxy: dict | None = None,
        sock: Any = None,
    ) -> Any:
        client = paramiko_module.SSHClient()
        client.set_missing_host_key_policy(paramiko_module.AutoAddPolicy())
        kwargs: dict[str, Any] = {}
        if sock is not None:
            kwargs["sock"] = sock
        elif proxy:
            kwargs["sock"] = SSHPlugin._open_socks5(proxy, host, port, timeout)
        client.connect(
            hostname=host,
            port=port,
            username=user,
            password=pwd,
            key_filename=key,
            timeout=timeout,
            **kwargs,
        )
        return client

    @staticmethod
    def _open_socks5(proxy: dict, host: str, port: int, timeout: float) -> Any:
        proxy_host = str(proxy.get("host") or "").strip()
        proxy_port = int(proxy.get("port") or 1080)
        if not proxy_host:
            raise ValueError("proxy.host 不能为空")
        if str(proxy.get("type") or "socks5").lower() not in ("socks5", "socks"):
            raise ValueError("目前仅支持 SOCKS5 代理")
        try:
            import socks
        except ImportError as exc:
            raise RuntimeError("SOCKS5 代理需要安装 PySocks") from exc
        return socks.create_connection(
            (host, port),
            timeout=timeout,
            proxy_type=socks.SOCKS5,
            proxy_addr=proxy_host,
            proxy_port=proxy_port,
            proxy_username=proxy.get("user"),
            proxy_password=proxy.get("pwd"),
        )

    @staticmethod
    def _write(stdin: Any, channel: Any, data: str, *, newline: bool) -> None:
        text = str(data) + ("\n" if newline else "")
        if stdin is not None and hasattr(stdin, "write"):
            stdin.write(text)
            if hasattr(stdin, "flush"):
                stdin.flush()
        else:
            channel.sendall(text)

    @staticmethod
    def _read_channel(
        channel: Any, *, timeout: float, require_exit: bool
    ) -> tuple[str, str, int, bool, bool]:
        """读取通道：返回 (stdout, stderr, exit_code, exited, timed_out)。

        ``require_exit=True`` 用于非交互命令：只有 exit-status 就绪且无剩余数据
        才认为命令结束；``require_exit=False`` 用于交互通道：无输出超过 timeout
        即返回当前快照。
        """
        out: list[str] = []
        err: list[str] = []
        start = time.monotonic()
        last_data = start
        exited = False
        timed_out = False
        while True:
            now = time.monotonic()
            ready = channel.exit_status_ready()
            has_out = channel.recv_ready()
            has_err = channel.recv_stderr_ready()
            if has_out:
                out.append(channel.recv(65536).decode("utf-8", "replace"))
                last_data = now
            if has_err:
                err.append(channel.recv_stderr(65536).decode("utf-8", "replace"))
                last_data = now
            if ready and not has_out and not has_err:
                exited = True
                break
            if require_exit:
                if now - start > timeout:
                    timed_out = True
                    break
            elif now - last_data > timeout:
                break
            time.sleep(0.02)
        code = 0
        if exited:
            try:
                code = int(channel.recv_exit_status())
            except Exception:  # noqa: BLE001
                code = -1
        return strip_ansi("".join(out)), strip_ansi("".join(err)), code, exited, timed_out

    @staticmethod
    def _safe_close(resource: Any) -> None:
        if resource is None:
            return
        try:
            resource.close()
        except Exception:  # noqa: BLE001
            pass

    def _close_connection(self, conn: SSHConnection) -> None:
        for state in list(conn.channels.values()):
            self._safe_close(state.channel)
        conn.channels.clear()
        self._safe_close(conn.client)
        self._safe_close(conn.jump_shell)
        self._safe_close(conn.jump_client)


plugin = SSHPlugin()


__all__ = ["SSHPlugin", "SSHConnection", "plugin"]
