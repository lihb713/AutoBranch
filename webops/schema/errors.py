"""M3 schema 命名空间：可分类异常（契约 §5.3.5/§5.3.2/§5.7.7）。

类型校验失败触发 ``SchemaTypeError``（断言失败语义），越权访问触发
``SchemaScopeError``，路径格式错误触发 ``SchemaPathError``。统一基类
``SchemaError`` 供 M7 编排器捕获后沿行为树传播并终止流程（§5.7.7）。
"""

from __future__ import annotations


class SchemaError(Exception):
    """schema 命名空间错误基类（M7 可捕获并沿树传播）。"""


class SchemaPathError(SchemaError):
    """路径格式错误（空路径、空分段、变量名与子块名冲突等）。"""


class SchemaScopeError(SchemaError):
    """越权访问（目标帧不是自身帧或直接子帧）。"""


class SchemaTypeError(SchemaError):
    """类型断言失败（写入/提取时值不符合声明类型，契约 §5.3.5）。"""
