"""任务 4.1/4.2/4.3/4.4：会话消息累积、全量携带、工具回填与多轮循环。"""

from __future__ import annotations

from fake_transport import chat_response

from autobranch.llm.models import ToolResult, ToolSpec
from autobranch.llm.session import LLMSession


def make_session(config, fake, system="你是助手"):
    return LLMSession(config=config, system_prompt=system, transport=fake)


def test_add_user_message_accumulates(config, fake):
    """4.1 add_user_message 按序累积消息。"""
    session = make_session(config, fake)
    assert session.message_count == 0
    session.add_user_message("第一条")
    session.add_user_message("第二条")
    assert session.message_count == 2


def test_request_carries_full_history(config, fake):
    """4.2 多次请求后报文包含全部历史消息且顺序不变。"""
    fake.responses = [chat_response(text="a"), chat_response(text="b"), chat_response(text="c")]
    session = make_session(config, fake)
    session.add_user_message("问题1")
    session.request()
    session.add_user_message("问题2")
    session.request()
    session.add_user_message("问题3")
    session.request()

    last = fake.last_request.json()
    roles = [m["role"] for m in last["messages"]]
    # system, 问题1, assistant(a), 问题2, assistant(b), 问题3
    # （第 3 次请求的 assistant(c) 在报文发出后才追加，不在本次报文中）
    assert roles == ["system", "user", "assistant", "user", "assistant", "user"]
    contents = [m["content"] for m in last["messages"] if m["role"] == "user"]
    assert contents == ["问题1", "问题2", "问题3"]


def test_tool_result_round_trip(config, fake):
    """4.3 助手请求工具 → 回填 → 再请求，id 正确配对且结果在上下文中。"""
    fake.responses = [
        chat_response(
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "lookup", "arguments": "{}"},
                }
            ]
        ),
        chat_response(text="结果：42"),
    ]
    session = make_session(config, fake)
    session.add_user_message("查一下值")
    first = session.request(tools=[ToolSpec(name="lookup", description="查询")])
    assert first.tool_calls[0].id == "call_1"

    session.add_tool_result("call_1", ToolResult(call_id="call_1", content="42"))
    second = session.request(tools=[ToolSpec(name="lookup", description="查询")])
    assert second.text == "结果：42"

    body = fake.last_request.json()
    tool_msgs = [m for m in body["messages"] if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_call_id"] == "call_1"
    assert tool_msgs[0]["content"] == "42"


def test_multi_round_tool_loop(config, fake):
    """4.4 多轮循环后上下文持续累积、每轮工具 id 与结果正确配对。"""
    fake.responses = [
        chat_response(
            tool_calls=[
                {
                    "id": "call_a",
                    "type": "function",
                    "function": {"name": "step1", "arguments": "{}"},
                }
            ]
        ),
        chat_response(
            tool_calls=[
                {
                    "id": "call_b",
                    "type": "function",
                    "function": {"name": "step2", "arguments": '{"v":"42"}'},
                }
            ]
        ),
        chat_response(text="完成"),
    ]
    tools = [ToolSpec(name="step1", description="s1"), ToolSpec(name="step2", description="s2")]
    session = make_session(config, fake)
    session.add_user_message("跑流程")

    r1 = session.request(tools=tools)
    assert r1.tool_calls[0].id == "call_a"
    session.add_tool_result("call_a", "step1-ok")

    r2 = session.request(tools=tools)
    assert r2.tool_calls[0].id == "call_b"
    session.add_tool_result("call_b", "step2-ok")

    r3 = session.request(tools=tools)
    assert r3.text == "完成"

    body = fake.last_request.json()
    tool_msgs = [m for m in body["messages"] if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_msgs] == ["call_a", "call_b"]
    assert [m["content"] for m in tool_msgs] == ["step1-ok", "step2-ok"]
    # 助手工具调用消息也保留在上下文中
    assistant_msgs = [m for m in body["messages"] if m["role"] == "assistant"]
    assert len(assistant_msgs) == 2
    assert assistant_msgs[0]["tool_calls"][0]["id"] == "call_a"


def test_no_tools_returns_plain_text(config, fake):
    fake.responses = [chat_response(text="纯文本回复")]
    session = make_session(config, fake)
    session.add_user_message("你好")
    resp = session.request()  # 不传 tools
    assert resp.text == "纯文本回复"
    assert not resp.has_tool_calls


def test_request_sends_stable_x_opencode_session(config, fake):
    """每个会话发送稳定的 ``x-opencode-session`` 请求头（同一会话多轮一致）。

    opencode.ai/zen/go 网关要求该头用于路由与提示缓存；缺省自动生成 UUID。
    """
    fake.responses = [chat_response(text="a"), chat_response(text="b")]
    session = make_session(config, fake)
    session.add_user_message("q1")
    session.request()
    session.add_user_message("q2")
    session.request()

    h1 = fake.requests[0].headers
    h2 = fake.requests[1].headers
    assert h1["x-opencode-session"]
    assert h1["x-opencode-session"] == h2["x-opencode-session"]


def test_config_session_id_reused_across_sessions(config, fake):
    """配置提供 ``session_id`` 时，不同 LLMSession 实例复用同一 ID。"""
    fake.responses = [chat_response(text="a"), chat_response(text="b")]
    session_a = LLMSession(
        config=config, system_prompt="你", transport=fake, session_id="fixed-session"
    )
    session_a.add_user_message("q")
    session_a.request()
    session_b = LLMSession(
        config=config, system_prompt="你", transport=fake, session_id="fixed-session"
    )
    session_b.add_user_message("q")
    session_b.request()
    assert fake.requests[0].headers["x-opencode-session"] == "fixed-session"
    assert fake.requests[1].headers["x-opencode-session"] == "fixed-session"
