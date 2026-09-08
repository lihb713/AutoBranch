"""WebOps schema 命名空间（M3）。

行为树变量命名空间机制：每次块引用创建独立 schema 帧（``SchemaFrame``），
管理变量读写（严格作用域）、传参返回值、配置参数继承与类型校验、
页面变量。纯逻辑、无外部依赖，可独立测试。

对外公开的接口：
- ``SchemaSpace``（``enter_block`` / ``exit_block`` / ``write`` / ``read`` /
  ``set_config`` / ``resolve_config`` / ``current_page`` / ``page_refs``）
- ``SchemaFrame`` / ``BlockDecl`` / ``PageRef`` / ``Value``
- ``SUPPORTED_TYPES`` / ``check_type`` / ``infer_type`` / ``validate_type_name``
- 可分类异常：``SchemaError`` / ``SchemaPathError`` / ``SchemaScopeError`` /
  ``SchemaTypeError``
"""

from webops.schema.errors import (
    SchemaError,
    SchemaPathError,
    SchemaScopeError,
    SchemaTypeError,
)
from webops.schema.models import BlockDecl, PageRef, SchemaFrame, Value
from webops.schema.space import SchemaSpace
from webops.schema.types import (
    SUPPORTED_TYPES,
    check_type,
    infer_type,
    validate_type_name,
)

__all__ = [
    "SchemaSpace",
    "SchemaFrame",
    "BlockDecl",
    "PageRef",
    "Value",
    "SUPPORTED_TYPES",
    "check_type",
    "infer_type",
    "validate_type_name",
    "SchemaError",
    "SchemaPathError",
    "SchemaScopeError",
    "SchemaTypeError",
]
