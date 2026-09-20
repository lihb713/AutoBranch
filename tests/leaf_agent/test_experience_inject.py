"""经验回灌叶子注入测试（Change C 任务 1.2/2.2/2.3）。

覆盖：build_user_message 参考段渲染与 None 不渲染；execute_leaf 命中经验注入参考段；
LeafTrace.llm_input["description"] 记录替换后描述（非模板）。
"""

from __future__ import annotations

import pytest
from fake_transport import FakeTransport, chat_response
from leaf_agent_helpers import MockRegistry

from autobranch.leaf_agent import execute_leaf
from autobranch.leaf_agent.models import LeafContext
from autobranch.leaf_agent.prompts import build_user_message
from autobranch.llm import LLMConfig, LLMSession
from autobranch.parser.models import ActionNode
from autobranch.schema import SchemaSpace


@pytest.fixture
def llm_config() -> LLMConfig:
    return LLMConfig(base_url="https://api.test.example/v1", api_key="sk-test", model="m")


@pytest.fixture
def space() -> SchemaSpace:
    sp = SchemaSpace()
    sp.enter_frame("主流程")
    return sp


def test_build_user_message_reference_section():
    with_ref = build_user_message("描述", "图", reference="参考段文本")
    assert "参考段文本" in with_ref
    no_ref = build_user_message("描述", "图")
    assert "参考段文本" not in no_ref


def test_execute_leaf_injects_reference_and_records_resolved(llm_config, space):
    space.write(space._current, "this/user", "admin", "str")
    transport = FakeTransport(responses=[chat_response(text="结果: 成功")])

    def factory(cfg, system_prompt):
        return LLMSession(config=cfg, system_prompt=system_prompt, transport=transport)

    ctx = LeafContext(
        config=llm_config,
        registry=MockRegistry(),
        space=space,
        session_factory=factory,
        experience_lookup=lambda desc: f"参考经验: {desc}",
    )
    node = ActionNode(description="登录用户: Param.user")
    result = execute_leaf(node, ctx)
    assert result.status == "success"

    body = transport.last_request.json()
    joined = " ".join(m["content"] for m in body["messages"])
    # 命中经验 → 参考段进入用户消息（携带替换后的实际值）
    assert "参考经验: 登录用户: admin" in joined
    assert "Param." not in joined
    # 任务 1.2：LeafTrace 记录替换后描述（非模板）
    assert result.trace.llm_input["description"] == "登录用户: admin"


def test_execute_leaf_without_lookup_no_reference(llm_config, space):
    space.write(space._current, "this/user", "admin", "str")
    transport = FakeTransport(responses=[chat_response(text="结果: 成功")])

    def factory(cfg, system_prompt):
        return LLMSession(config=cfg, system_prompt=system_prompt, transport=transport)

    ctx = LeafContext(
        config=llm_config,
        registry=MockRegistry(),
        space=space,
        session_factory=factory,
        experience_lookup=None,
    )
    node = ActionNode(description="登录用户: Param.user")
    result = execute_leaf(node, ctx)
    body = transport.last_request.json()
    joined = " ".join(m["content"] for m in body["messages"])
    assert "参考经验" not in joined
    assert result.trace.llm_input["description"] == "登录用户: admin"
