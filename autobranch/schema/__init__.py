"""AutoBranch schema 命名空间（M3）。

行为树变量命名空间机制：每次文档引用创建独立 schema 帧（``SchemaFrame``），
管理变量读写（严格作用域）、传参返回值、配置参数继承与类型校验、
页面变量。纯逻辑、无外部依赖，可独立测试。

对外公开的接口：
- ``SchemaSpace``（``enter_frame`` / ``exit_frame`` / ``write`` / ``read`` /
  ``set_config`` / ``resolve_config`` / ``current_page`` / ``page_refs``）
- ``SchemaFrame`` / ``FrameDecl`` / ``PageRef`` / ``Value``
- ``TYPE_REGISTRY`` / ``check_type`` / ``coerce`` / ``infer_type`` /
  ``validate_type_name``
- 可分类异常：``SchemaError`` / ``SchemaPathError`` / ``SchemaScopeError`` /
  ``SchemaTypeError``
"""

from autobranch.schema.errors import (
    SchemaError,
    SchemaPathError,
    SchemaScopeError,
    SchemaTypeError,
)
from autobranch.schema.models import FrameDecl, PageRef, SchemaFrame, Value
from autobranch.schema.space import SchemaSpace
from autobranch.schema.types import (
    TYPE_REGISTRY,
    check_type,
    coerce,
    infer_type,
    validate_type_name,
)

__all__ = [
    "SchemaSpace",
    "SchemaFrame",
    "FrameDecl",
    "PageRef",
    "Value",
    "TYPE_REGISTRY",
    "check_type",
    "coerce",
    "infer_type",
    "validate_type_name",
    "SchemaError",
    "SchemaPathError",
    "SchemaScopeError",
    "SchemaTypeError",
]
