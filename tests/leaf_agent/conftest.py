"""M6 叶子 agent 测试共享 fixture（假 LLM 传输桩 + 假 M5 引擎桩）。

假引擎/慢传输/结果构造器位于 ``tests/leaf_agent_helpers.py``，经
``pythonpath=["tests"]`` 顶层导入；``config`` / ``fake`` 复用根级
``tests/conftest.py`` 提供的 fixture。
"""

from __future__ import annotations

import pytest
from leaf_agent_helpers import StubEngine


@pytest.fixture
def stub_engine() -> StubEngine:
    """假 M5 引擎：默认返回失败结果，测试内按函数名配置返回序列。"""
    return StubEngine()
