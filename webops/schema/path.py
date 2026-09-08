"""M3 schema 命名空间：路径解析工具（契约 §5.3/§5.2）。

路径按 ``/`` 分层：首段标识目标帧（``$this``、自身块名或直接子块名），
剩余段为帧内变量名（仅允许单段）。越权访问（祖先/兄弟/孙子）在解析时
即被拒绝并抛 ``SchemaScopeError``。
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

    目标帧只允许自身帧或直接子帧（契约 §5.3.2）；其余（祖先/兄弟/孙子）
    一律视为越权并抛 ``SchemaScopeError``。
    """
    segments = split_segments(path)
    first = segments[0]
    cur = frame
    moved = 0
    if _is_self(first) or first == frame.block_name:
        rest = segments[1:]
    elif first in frame.children:
        cur = frame.children[first]
        moved = 1
        rest = segments[1:]
    else:
        raise SchemaScopeError(f"越权访问: 目标帧 {first!r} 不是自身或直接子块")
    if rest and rest[0] in cur.children:
        if moved:
            raise SchemaScopeError(f"越权访问孙子帧: {path}")
        cur = cur.children[rest[0]]
        rest = rest[1:]
    if len(rest) != 1:
        raise SchemaScopeError(f"越权访问: {path}")
    var = rest[0]
    if var in cur.children:
        raise SchemaPathError(f"变量名与子块名冲突: {var!r}")
    return cur, var
