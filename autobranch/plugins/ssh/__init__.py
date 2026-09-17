"""SSH 插件（M7 插件集）：创建 / 关闭远程会话、在远程主机执行命令。

会话对象（``SSHConnection``）作为泛型对象值在变量中存储与传递。函数只
返回值、不写变量。命令非零退出码 / 超时返回失败结果。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from autobranch.plugin_system import FunctionResult, PluginBase, engine_function


def _params(required: tuple[str, ...], **props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(required)}


@dataclass
class SSHConnection:
    """远程 SSH 会话对象（泛型 ``object`` 值）。"""

    id: str
    client: Any = field(repr=False)

    def __str__(self) -> str:
        return f"SSHConnection(id={self.id[:8]}…)"

    def __repr__(self) -> str:
        return str(self)


class SSHPlugin(PluginBase):
    """SSH 能力：会话创建 / 关闭、远程执行。"""

    name = "ssh"
    description = (
        "SSH 远程能力：创建会话（create_session）、执行命令（ssh_exec）、"
        "关闭会话（close_session）"
    )

    def __init__(self) -> None:
        self._connections: dict[str, SSHConnection] = {}

    def init(self, runtime: Any = None) -> None:
        pass

    def release(self) -> None:
        for conn in list(self._connections.values()):
            try:
                conn.client.close()
            except Exception:  # noqa: BLE001
                pass
        self._connections.clear()

    @engine_function(
        name="create_session",
        description="创建远程 SSH 会话（返回会话对象，可存入变量供 ssh_exec / close_session 使用）",
        parameters=_params(
            ("host",),
            host={"type": "string", "description": "远程主机 IP / 域名"},
            port={"type": "integer", "description": "SSH 端口（默认 22）"},
            user={"type": "string", "description": "登录用户名"},
            pwd={"type": "string", "description": "密码（与密钥二选一）"},
            key={"type": "string", "description": "私钥文件路径（与密码二选一）"},
            timeout={"type": "number", "description": "连接超时秒数（默认 15）"},
        ),
        returns=("session",),
    )
    def create_session(
        self,
        host: str,
        port: int = 22,
        user: str = "root",
        pwd: str | None = None,
        key: str | None = None,
        timeout: float = 15.0,
    ) -> FunctionResult:
        try:
            import paramiko
        except ImportError:
            return FunctionResult.failure(
                "paramiko 未安装（ssh 插件依赖，请联系环境安装）", code="SSH_ERROR"
            )
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=host,
                port=port,
                username=user,
                password=pwd,
                key_filename=key,
                timeout=timeout,
            )
        except Exception as exc:  # noqa: BLE001
            return FunctionResult.failure(f"SSH 连接失败: {exc}", code="SSH_ERROR")
        conn = SSHConnection(id=uuid.uuid4().hex, client=client)
        self._connections[conn.id] = conn
        return FunctionResult.success(conn)

    @engine_function(
        name="ssh_exec",
        description="在远程会话执行命令，返回 stdout / stderr / 退出码（非零退出码为失败）",
        parameters=_params(
            ("session", "command"),
            session={"type": "string", "description": "会话对象（create_session 返回）"},
            command={"type": "string", "description": "要执行的命令"},
            timeout={"type": "number", "description": "命令超时秒数（默认 30）"},
        ),
        returns=("stdout", "stderr", "exit_code"),
    )
    def ssh_exec(
        self,
        session: SSHConnection,
        command: str,
        timeout: float = 30.0,
    ) -> FunctionResult:
        conn = self._find(session)
        if conn is None:
            return FunctionResult.failure("会话不存在或已关闭", code="SSH_ERROR")
        try:
            _stdin, stdout, stderr = conn.client.exec_command(
                command, timeout=timeout
            )
            out = stdout.read().decode("utf-8", "replace")
            err = stderr.read().decode("utf-8", "replace")
            code = stdout.channel.recv_exit_status()
        except Exception as exc:  # noqa: BLE001
            return FunctionResult.failure(f"命令执行失败: {exc}", code="SSH_ERROR")
        if code != 0:
            return FunctionResult.failure(
                f"命令退出码 {code}: {err}",
                code="SSH_ERROR",
                stdout=out,
                stderr=err,
                exit_code=code,
            )
        return FunctionResult.success(out, err, code)

    @engine_function(
        name="close_session",
        description="关闭远程 SSH 会话",
        parameters=_params(("session",), session={"type": "string", "description": "会话对象"}),
    )
    def close_session(self, session: SSHConnection) -> FunctionResult:
        conn = self._find(session)
        if conn is None:
            return FunctionResult.failure("会话不存在或已关闭", code="SSH_ERROR")
        try:
            conn.client.close()
        except Exception:  # noqa: BLE001
            pass
        self._connections.pop(conn.id, None)
        return FunctionResult.success()

    def _find(self, session: SSHConnection) -> SSHConnection | None:
        if not isinstance(session, SSHConnection):
            return None
        return self._connections.get(session.id)


plugin = SSHPlugin()


__all__ = ["SSHPlugin", "SSHConnection", "plugin"]
