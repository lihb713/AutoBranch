"""M3 schema 命名空间：路径解析工具（契约 §5.3/§5.2）。

变量寻址**无层级概念**（一文档一树，get/set 均针对当前文档执行帧）：
- 单段裸名 ``param1`` → 当前帧内变量；
- 兼容旧式 ``this/param1`` / ``$this/param1`` / ``自身名/param1``。

任何跨帧多段路径（祖先/兄弟/子帧/孙子）在解析时即被拒绝并抛
``SchemaScopeError``——跨帧传参一律经 ref 的 args/returns，不通过帧路径读写。
"""

from __future__ import annotations

from autobranch.schema.errors import SchemaPathError, SchemaScopeError
from autobranch.schema.models import SchemaFrame

THIS_TOKEN = "$this"

#: 兼容标记：``this`` / ``$this`` 均指向当前帧。
_SELF_TOKENS = frozenset({THIS_TOKEN, "this", "$this"})


def _is_self(token: str) -> bool:
    return token in _SELF_TOKENS


def split_segments(path: str) -> tuple[str, ...]:
    """按 ``/`` 分层拆分路径。

    空路径与空分段（首尾斜杠、连续斜杠）均被拒绝——变量名不得含 ``/``。
    """
    if not isinstance(path, str) or not path:
        raise SchemaPathError("路径不能为空")
    segments = tuple(path.split("/"))
    if any(not seg for seg in segments):
        raise SchemaPathError(f"路径含空分段: {path!r}")
    return segments


def resolve_target(frame: SchemaFrame, path: str) -> tuple[SchemaFrame, str]:
    """解析路径，返回 ``(目标帧, 帧内变量名)``。

    仅允许单段：**裸变量名**（``param1``，作用于当前帧）或兼容式 ``this/param1``
    /``$this/param1``/``自身名/param1``。任何跨帧多段路径（子帧/祖先/兄弟/孙子）
    一律视为越权并抛 ``SchemaScopeError``——跨帧传参经 ref 的 args/returns，
    不在帧路径上读写。
    """
    segments = split_segments(path)
    if len(segments) == 1:
        var = segments[0]
        if var in frame.children:
            raise SchemaPathError(f"变量名与子帧名冲突: {var!r}")
        return frame, var
    first = segments[0]
    if not (_is_self(first) or first == frame.name):
        raise SchemaScopeError(f"越权访问: 目标帧 {first!r} 不是自身")
    rest = segments[1:]
    if len(rest) != 1:
        raise SchemaScopeError(
            f"越权访问: {path}（仅支持单段变量名，跨帧传参经 ref args/returns）"
        )
    var = rest[0]
    if var in frame.children:
        raise SchemaPathError(f"变量名与子帧名冲突: {var!r}")
    return frame, var
