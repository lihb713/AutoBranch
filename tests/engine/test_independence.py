"""M5 任务 6.4：模块独立性——引擎函数层不依赖 M6/M7（叶子 agent/编排器）。

验收标准：M5 单元测试全部通过且不依赖 M6/M7 模块（测试以 mock M1/M4/M3
为主）。本文件静态校验 `webops/engine` 源码不引用 M6/M7 相关模块名。
"""

from __future__ import annotations

import pathlib

import webops.engine
from webops.engine import ENGINE_TOOLS, EngineFunctions, OpResult

# M6/M7 相关模块名（叶子 agent 执行 / 编排器 / 管理后端）
_FORBIDDEN_REFERENCES = ("webops.agent", "webops.orchestrator", "webops.server")


def test_engine_source_has_no_m6_m7_imports():
    package_dir = pathlib.Path(webops.engine.__file__).parent
    assert package_dir.name == "engine"
    for source in package_dir.glob("*.py"):
        text = source.read_text(encoding="utf-8")
        for ref in _FORBIDDEN_REFERENCES:
            assert ref not in text, f"{source.name} 引用了 {ref}"


def test_engine_registry_and_entry_importable():
    assert len(ENGINE_TOOLS) == 17
    assert callable(EngineFunctions)
    assert OpResult(True).ok is True
