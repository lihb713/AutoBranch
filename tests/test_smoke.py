"""任务 8.2：可选冒烟测试——连接真实 OpenAI 兼容端点。

通过环境变量注入密钥，未配置时自动跳过（可跳过验收项）。
密钥不写入任何代码/文档/仓库文件。

环境变量：
- ``AUTOBRANCH_LLM_BASE_URL``：OpenAI 兼容端点（默认 https://api.deepseek.com）
- ``AUTOBRANCH_LLM_API_KEY``：API 密钥（缺失则跳过）
- ``AUTOBRANCH_LLM_MODEL``：模型名（默认 deepseek-chat）
"""

from __future__ import annotations

import os

import pytest

from autobranch.llm.config import LLMConfig
from autobranch.llm.models import ToolSpec
from autobranch.llm.session import LLMSession

pytestmark = pytest.mark.smoke

BASE_URL = os.environ.get("AUTOBRANCH_LLM_BASE_URL", "https://api.deepseek.com")
API_KEY = os.environ.get("AUTOBRANCH_LLM_API_KEY", "")
MODEL = os.environ.get("AUTOBRANCH_LLM_MODEL", "deepseek-chat")


def test_smoke_real_endpoint():
    """真实请求冒烟：需设置 AUTOBRANCH_LLM_API_KEY 才运行。"""
    if not API_KEY:
        pytest.skip("未配置 AUTOBRANCH_LLM_API_KEY，跳过冒烟测试")
    config = LLMConfig(base_url=BASE_URL, api_key=API_KEY, model=MODEL)
    session = LLMSession(config=config, system_prompt="你是简洁的助手。")
    session.add_user_message("请只回复：PONG")
    resp = session.request()
    assert isinstance(resp.text, str)
    assert resp.text.strip() != ""


def test_smoke_real_tool_call():
    """真实工具调用冒烟：模型应返回合法参数的 function_call。"""
    if not API_KEY:
        pytest.skip("未配置 AUTOBRANCH_LLM_API_KEY，跳过冒烟测试")
    config = LLMConfig(base_url=BASE_URL, api_key=API_KEY, model=MODEL)
    session = LLMSession(config=config, system_prompt="你是工具助手。")
    session.add_user_message("把 2 加 3 的和用计算工具算出来")
    resp = session.request(
        tools=[ToolSpec(name="add", description="计算两数之和", parameters={"type": "object"})]
    )
    assert resp.has_tool_calls, f"期望工具调用，实际 text={resp.text!r}"
    assert resp.tool_calls[0].name == "add"
    assert resp.tool_calls[0].id
