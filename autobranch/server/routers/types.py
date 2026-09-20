"""类型可构造性路由（GET /api/types，Change A 任务 4.4）。

返回全部类型 token 与 ``constructible``（可否由文本构造）标志，由后端类型系统
单点派生（``TypeSpec.cast is not None``），前端类型 token / 入参表单 / 执行按钮
约束均自此派生。
"""

from __future__ import annotations

from fastapi import APIRouter

from autobranch.schema import TYPE_REGISTRY
from autobranch.server.schemas.run import TypeInfoOut

router = APIRouter(prefix="/api/types", tags=["types"])


@router.get("", response_model=list[TypeInfoOut])
def list_types():
    """全部类型 token + 可构造标志（str/int/float/bool 可构造，page_ref/object 不可）。"""
    return [
        TypeInfoOut(token=token, constructible=spec.cast is not None)
        for token, spec in TYPE_REGISTRY.items()
    ]


__all__ = ["router"]
