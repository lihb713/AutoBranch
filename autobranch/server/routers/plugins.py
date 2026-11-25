"""插件管理路由（列表 / 详情 / 新增 / 更新 / 删除 / 校验 / 关联查询）。

只做 HTTP 编排（状态码 / service 调用），业务逻辑在 service 层。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from autobranch.server.schemas.plugin import (
    FunctionInfo,
    PluginCheckIn,
    PluginCheckOut,
    PluginCreate,
    PluginDeleteOut,
    PluginDetailOut,
    PluginManifestOut,
    PluginOut,
    PluginUpdate,
)
from autobranch.server.services.plugins import PluginService

router = APIRouter(prefix="/api/plugins", tags=["plugins"])

PluginServiceDep = Annotated[PluginService, Depends()]


@router.get("", response_model=list[PluginOut])
def list_plugins(service: PluginServiceDep, include_manifest: bool = False):
    return service.list_all(include_manifest=include_manifest)


@router.post("/check", response_model=PluginCheckOut)
def check_plugin(payload: PluginCheckIn, service: PluginServiceDep):
    """校验插件源码（语法 + 约束 + 可加载），返回可定位错误明细。"""
    return service.check(payload.name, payload.source)


@router.post("", response_model=PluginOut, status_code=status.HTTP_201_CREATED)
def create_plugin(payload: PluginCreate, service: PluginServiceDep):
    return service.create(payload)


@router.get("/{name}/manifest", response_model=PluginManifestOut)
def get_manifest(name: str, service: PluginServiceDep):
    return PluginManifestOut.model_validate(service.get_manifest(name))


@router.get("/{name}/config", response_model=dict)
def get_config(name: str, service: PluginServiceDep):
    return service.get_config(name)


@router.put("/{name}/config", response_model=dict)
def update_config(name: str, config: dict, service: PluginServiceDep):
    return service.update_config(name, config)


@router.get("/{name}/functions", response_model=list[FunctionInfo])
def list_plugin_functions(name: str, service: PluginServiceDep):
    return service.list_functions_of(name)


@router.get("/{name}", response_model=PluginDetailOut)
def get_plugin(name: str, service: PluginServiceDep):
    return service.get_detail(name)


@router.put("/{name}", response_model=PluginOut)
def update_plugin(name: str, payload: PluginUpdate, service: PluginServiceDep):
    return service.update(name, payload)


@router.delete("/{name}", response_model=PluginDeleteOut)
def delete_plugin(name: str, service: PluginServiceDep):
    """删除自定义插件；返回引用该插件的行为树名列表（引用内容保留）。"""
    affected = service.delete(name)
    return PluginDeleteOut(affected_trees=affected)


@router.get("/{name}/references", response_model=list[str])
def list_references(name: str, service: PluginServiceDep):
    """列出引用该插件函数的行为树（删除前提示用）。"""
    return service.references(name)


__all__ = ["router"]
