"""文件插件（M7 插件集）：文件读写 / 对比 / 路径操作。

路径以引擎工作目录为基址（相对路径）；读取失败（不存在 / 无权限）返回
失败结果（含原因）；单文件大小上限 10MB。函数只返回值、不写变量。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

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
    """文件能力：读 / 写 / 对比。"""

    name = "file"
    description = "文件能力：读取（read）、写入（write）、对比（diff）"

    @engine_function(
        name="read",
        description="读取文件内容（UTF-8；相对路径以引擎工作目录为基址）",
        parameters=_params(("path",), path={"type": "string", "description": "文件路径"}),
        returns=("content",),
    )
    def read(self, path: str) -> FunctionResult:
        try:
            if os.path.getsize(path) > MAX_FILE_SIZE:
                return FunctionResult.failure(f"文件过大（>10MB）: {path}", code="FILE_ERROR")
            with open(path, encoding="utf-8") as f:
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
            with open(path, "w", encoding="utf-8") as f:
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
        returns=("diff",),
    )
    def diff(self, file_a: str, file_b: str) -> FunctionResult:
        try:
            with open(file_a, encoding="utf-8") as f:
                a_lines = f.read().splitlines()
            with open(file_b, encoding="utf-8") as f:
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
