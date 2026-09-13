"""M3 schema 命名空间：路径解析工具（契约 §5.3/§5.2）。

路径按 ``/`` 分层，仅支持单段寻址：首段标识当前帧（``$this`` 或自身
块名），第二段为帧内变量名。任何跨帧多段路径（祖先/兄弟/子块/孙子）
在解析时即被拒绝并抛 ``SchemaScopeError``——跨帧传参一律经 ref 的
args/returns，不通过帧路径读写。
"""

from __future__ import annotations

from webops.schema.errors import SchemaPathError, SchemaScopeError
from webops.schema.models import SchemaFrame

THIS_TOKEN = "$this"

#: 兼容标记：新语法 ``this``（无 $）与内部旧标记 ``$this`` 均指向当前帧。
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

    仅允许单段寻址：目标帧必须为当前帧自身（``this``/``$this``/自身
    块名），且路径仅含一个变量名段。任何跨帧多段路径（子块/祖先/兄弟/
    孙子）一律视为越权并抛 ``SchemaScopeError``——跨帧传参经 ref 的
    args/returns，不在帧路径上读写。
    """
    segments = split_segments(path)
    first = segments[0]
    if not (_is_self(first) or first == frame.name):
        raise SchemaScopeError(f"越权访问: 目标帧 {first!r} 不是自身")
    rest = segments[1:]
    if len(rest) != 1:
        raise SchemaScopeError(
            f"越权访问: {path}（仅支持单段 this/<名>，跨帧传参经 ref args/returns）"
        )
    var = rest[0]
    if var in frame.children:
        raise SchemaPathError(f"变量名与子块名冲突: {var!r}")
    return frame, var
