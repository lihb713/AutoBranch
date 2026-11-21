"""文件插件（M7 插件集）：文件读写 / 对比 / 路径操作。

路径以引擎工作目录为基址（相对路径）；读取失败（不存在 / 无权限）返回
失败结果（含原因）；单文件大小上限 10MB。函数只返回值、不写变量。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from autobranch.plugin_system import FunctionResult, PluginBase, engine_function

MAX_FILE_SIZE = 10 * 1024 * 1024


def _params(required: tuple[str, ...], **props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(required)}


@dataclass(frozen=True)
class FileDiff:
    """文件对比结果。"""

    file_a: str
    file_b: str
    same: bool
    lines: tuple[str, ...] = ()

    def __str__(self) -> str:
        if self.same:
            return f"FileDiff(same=True, {self.file_a} == {self.file_b})"
        return f"FileDiff(same=False, {len(self.lines)} 处差异)"

    def __repr__(self) -> str:
        return str(self)


class FilePlugin(PluginBase):
    """文件能力：读 / 写 / 对比 + 文件管理（API/前端/存储/配置）。"""

    name = "file"
    description = "文件能力：读取、写入、对比、文件管理"

    def __init__(self, storage_dir: str | None = None) -> None:
        self._service: Any = None
        self._max_file_size = MAX_FILE_SIZE
        self._custom_storage = storage_dir is not None
        self._storage_dir = storage_dir or os.path.join(os.path.dirname(__file__), "data")
        os.makedirs(self._storage_dir, exist_ok=True)

    # ------------------------------------------------------------ 模块化扩展

    def init(self, runtime: Any = None) -> None:
        if self._custom_storage:
            from .service import FileService

            self._service = FileService(self._storage_dir, max_file_size=self._max_file_size)
            return
        from .store import get_service

        self._service = get_service()
        self._service.max_file_size = self._max_file_size
        self._storage_dir = self._service.storage_root

    def register_routes(self, app: Any) -> None:
        from .api import create_file_router

        app.include_router(
            create_file_router(self._service),
            prefix="/api/plugins/file",
            tags=["file"],
        )

    def register_models(self, base: Any) -> None:
        from . import models  # noqa: F401 - import 即注册到 Base.metadata

    @property
    def frontend_manifest(self) -> dict[str, Any] | None:
        return {
            "pages": [
                {
                    "route": "/file",
                    "label": "文件管理",
                    "component": "FileManager",
                    "icon": "folder",
                }
            ]
        }

    @property
    def storage_dir(self) -> str | None:
        return "data"

    @property
    def config_schema(self) -> list[dict[str, Any]] | None:
        return [
            {
                "key": "max_file_size",
                "label": "最大文件大小(MB)",
                "type": "number",
                "default": 10,
                "required": False,
                "description": "单文件大小上限",
            }
        ]

    def get_config(self) -> dict[str, Any]:
        return {"max_file_size": self._max_file_size // (1024 * 1024)}

    def set_config(self, config: dict[str, Any]) -> None:
        if "max_file_size" in config:
            mb = float(config["max_file_size"])
            if mb <= 0:
                raise ValueError("max_file_size 必须大于 0")
            self._max_file_size = int(mb * 1024 * 1024)
            if self._service is not None:
                self._service.max_file_size = self._max_file_size
            try:
                from . import store

                if store.SERVICE is not None:
                    store.SERVICE.max_file_size = self._max_file_size
            except Exception:  # noqa: BLE001
                pass


    @engine_function(
        name="md5",
        description="计算文件管理根目录下文件的 MD5（相对路径）",
        parameters=_params(("path",), path={"type": "string", "description": "相对文件路径"}),
        returns={"md5": "str"},
    )
    def md5(self, path: str) -> FunctionResult:
        try:
            from .service import FileService

            return FunctionResult.success(FileService._md5_file(self._resolve_path(path)))
        except Exception as exc:  # noqa: BLE001
            return FunctionResult.failure(f"计算 MD5 失败: {exc}", code="FILE_ERROR")

    @engine_function(
        name="list_dir",
        description="列出文件管理平台指定目录的直接子目录与文件（path 为空表示根目录）",
        parameters=_params(
            ("path",),
            path={"type": "string", "description": "平台内目录路径（空=根目录）"},
        ),
        returns={"entries": "array"},
    )
    def list_dir(self, path: str = "") -> FunctionResult:
        from .store import get_service, session_scope

        try:
            with session_scope() as db:
                return FunctionResult.success(get_service().list_entries(db, path))
        except Exception as exc:  # noqa: BLE001
            return FunctionResult.failure(f"列出目录失败: {exc}", code="FILE_ERROR")

    @engine_function(
        name="mkdir",
        description="在文件管理平台创建目录（自动创建父目录）",
        parameters=_params(
            ("path",),
            path={"type": "string", "description": "目录路径，如 reports/2026"},
        ),
        returns={"directory": "object"},
    )
    def mkdir(self, path: str) -> FunctionResult:
        from .store import get_service, session_scope

        try:
            with session_scope() as db:
                return FunctionResult.success(get_service().create_directory(db, path))
        except Exception as exc:  # noqa: BLE001
            return FunctionResult.failure(f"创建目录失败: {exc}", code="FILE_ERROR")

    @engine_function(
        name="rmdir",
        description="删除文件管理平台目录（recursive=true 时连同内容删除）",
        parameters=_params(
            ("path",),
            path={"type": "string", "description": "目录路径"},
            recursive={"type": "boolean", "description": "是否递归删除（默认 true）"},
        ),
    )
    def rmdir(self, path: str, recursive: bool = True) -> FunctionResult:
        from .store import get_service, session_scope

        try:
            with session_scope() as db:
                service = get_service()
                record = service.get_directory_by_path(db, path)
                if record is None:
                    return FunctionResult.failure(f"目录不存在: {path}", code="FILE_ERROR")
                service.delete_directory(db, record["id"], recursive=bool(recursive))
            return FunctionResult.success()
        except Exception as exc:  # noqa: BLE001
            return FunctionResult.failure(f"删除目录失败: {exc}", code="FILE_ERROR")

    @engine_function(
        name="mvdir",
        description="重命名/移动文件管理平台目录（同步移动其中文件路径）",
        parameters=_params(
            ("path", "new_path"),
            path={"type": "string", "description": "原目录路径"},
            new_path={"type": "string", "description": "新目录路径"},
        ),
        returns={"directory": "object"},
    )
    def mvdir(self, path: str, new_path: str) -> FunctionResult:
        from .store import get_service, session_scope

        try:
            with session_scope() as db:
                service = get_service()
                record = service.get_directory_by_path(db, path)
                if record is None:
                    return FunctionResult.failure(f"目录不存在: {path}", code="FILE_ERROR")
                return FunctionResult.success(
                    service.rename_directory(db, record["id"], new_path)
                )
        except Exception as exc:  # noqa: BLE001
            return FunctionResult.failure(f"移动目录失败: {exc}", code="FILE_ERROR")

    def _resolve_path(self, path: str) -> str:
        """把插件内路径限制在文件管理根目录（data/）下。"""
        from .service import normalize_path

        if os.path.isabs(str(path or "")):
            raise ValueError("路径必须是相对文件管理根目录的相对路径")
        normalized = normalize_path(path)
        base = os.path.realpath(self._storage_dir)
        full = os.path.realpath(
            os.path.join(base, *normalized.split("/")) if normalized else base
        )
        if full != base and not full.startswith(base + os.sep):
            raise ValueError("路径越界：文件操作限制在文件管理根目录下")
        return full

    @engine_function(
        name="read",
        description="读取文件内容（UTF-8；相对文件管理根目录的路径）",
        parameters=_params(("path",), path={"type": "string", "description": "文件路径"}),
        returns={"content": "str"},
    )
    def read(self, path: str) -> FunctionResult:
        try:
            full = self._resolve_path(path)
            if os.path.getsize(full) > self._max_file_size:
                return FunctionResult.failure(
                    f"文件过大（>{self._max_file_size // (1024 * 1024)}MB）: {path}",
                    code="FILE_ERROR",
                )
            with open(full, encoding="utf-8") as f:
                return FunctionResult.success(f.read())
        except Exception as exc:  # noqa: BLE001 - 读失败返回失败结果
            return FunctionResult.failure(f"读取文件失败: {exc}", code="FILE_ERROR")

    @engine_function(
        name="write",
        description="写入文件内容（UTF-8；覆盖已存在文件）",
        parameters=_params(
            ("path", "content"),
            path={"type": "string", "description": "文件路径"},
            content={"type": "string", "description": "要写入的内容"},
        ),
    )
    def write(self, path: str, content: str) -> FunctionResult:
        try:
            full = self._resolve_path(path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(content)
            return FunctionResult.success()
        except Exception as exc:  # noqa: BLE001
            return FunctionResult.failure(f"写入文件失败: {exc}", code="FILE_ERROR")

    @engine_function(
        name="diff",
        description="对比两个文本文件，返回是否相同与差异行",
        parameters=_params(
            ("file_a", "file_b"),
            file_a={"type": "string", "description": "文件 A 路径"},
            file_b={"type": "string", "description": "文件 B 路径"},
        ),
        returns={"diff": "object"},
    )
    def diff(self, file_a: str, file_b: str) -> FunctionResult:
        try:
            with open(self._resolve_path(file_a), encoding="utf-8") as f:
                a_lines = f.read().splitlines()
            with open(self._resolve_path(file_b), encoding="utf-8") as f:
                b_lines = f.read().splitlines()
        except Exception as exc:  # noqa: BLE001
            return FunctionResult.failure(f"读取对比文件失败: {exc}", code="FILE_ERROR")
        if a_lines == b_lines:
            return FunctionResult.success(FileDiff(file_a, file_b, True))
        diffs = tuple(
            f"- {a}\n+ {b}"
            for a, b in zip(a_lines, b_lines, strict=False)
            if a != b
        )
        return FunctionResult.success(FileDiff(file_a, file_b, False, diffs))


plugin = FilePlugin()


__all__ = ["FilePlugin", "FileDiff", "plugin"]
