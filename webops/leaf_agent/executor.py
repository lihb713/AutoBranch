"""M6 叶子 agent 执行器（M6 spec §5.2、契约 §5.7.2/§5.7.2.1）。

``execute_leaf(node, ctx)`` 以 agent 式驱动单个叶子节点执行：

1. 构建 M0 会话（系统提示词 + M5 引擎函数工具集）并注入用户消息（节点描述 +
   初始语义图）。
2. 循环：``session.request(tools)`` → 含工具调用则经 M5 ``EngineFunctions.call``
   执行、把 ``OpResult`` 作为工具结果回填 → 直到模型返回纯文本（最终回答）
   或触发引擎兜底终止条件。
3. 最终回答解析为 Action 的 ``status`` / Condition 的 ``bool_value``。
4. 错误边界（§5.7.2.1/§9.4）：函数失败（``OpResult(ok=False)``）回传 LLM 由
   其自行修正；``FatalBrowserError`` 终止整个流程；``LLMConnectionError`` /
   ``LLMTimeoutError`` 为程序侧失败。

错误来源分类（design D4 + 明确化）：
- 程序侧（``program``）：致命错误（浏览器崩溃）、LLM 连接/超时。
- LLM 侧（``llm``）：三类终止条件、决策不可解析、Action 报告的失败、
  其他 LLM 错误（含 token 预算超限）。
- Condition 的确定布尔判断（真/假）是正常节点结果，``error_source=None``。
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from webops.browser import OpResult
from webops.engine import ENGINE_TOOLS, FatalBrowserError
from webops.leaf_agent.models import LeafContext, LeafResult, ToolCallRecord
from webops.leaf_agent.prompts import (
    PROMPT_VERSION,
    DecisionError,
    build_system_prompt,
    build_user_message,
    parse_final_decision,
)
from webops.leaf_agent.terminator import LeafTermination, NoProgressTracker
from webops.llm import (
    LLMBudgetExceeded,
    LLMConnectionError,
    LLMError,
    LLMSession,
    LLMTimeoutError,
    ToolResult,
    ToolSpec,
)
from webops.parser.models import ActionNode, ConditionNode
from webops.reporting.models import LeafTrace
from webops.schema.errors import SchemaError


@dataclass
class _LeafOutcome:
    """内部执行结果（构建 ``LeafResult`` 前承载全部决策信息）。"""

    status: Literal["success", "failure"]
    bool_value: bool | None = None
    error_source: Literal["llm", "program"] | None = None
    terminator: str | None = None
    decision: str | None = None
    reasoning: list[str] = field(default_factory=list)
    records: list[ToolCallRecord] = field(default_factory=list)


#: ``[[get:path]]`` 读取引用（叶子执行前程序替换，M2 同款正则；path 裸变量名或兼容 this/名）
_GET_TMPL = re.compile(r"\[\[\s*get:\s*((?:this/)?[^\[\]]+?)\s*\]\]")


def _bare_name(path: str) -> str:
    """归一化为裸变量名：``this/param`` / ``$this/param`` → ``param``。"""
    p = (path or "").strip()
    for prefix in ("this/", "$this/"):
        if p.startswith(prefix):
            return p[len(prefix) :]
    return p


def _norm_path(path: str) -> str:
    """把 `$this/`/`this/` 前缀归一化为裸变量名（extract target 与 set_targets 比较用）。"""
    return _bare_name(path)


def _resolve_get_refs(description: str, ctx: LeafContext) -> tuple[str, str | None]:
    """叶子执行前把 ``[[get:path]]`` 替换为 blackboard 真实值（确定性）。

    返回 ``(替换后文本, None)``；读取失败（变量未定义）返回
    ``(原文, 错误说明)``——该叶子应直接 FAILURE，不让 LLM 猜测。
    描述不含 ``[[get:...]]`` 时不做替换（即使未注入 space 也正常执行）。
    """
    if not _GET_TMPL.search(description):
        return description, None
    if ctx.space is None:
        return description, "变量读取依赖 SchemaSpace（未注入 space）"
    frame = ctx.space._current
    replaced = description
    for match in _GET_TMPL.finditer(description):
        var = _bare_name(match.group(1))
        if not var:
            continue
        try:
            value = ctx.space.read(frame, var)
        except SchemaError as exc:
            return description, f"变量读取失败（{var}）: {exc}"
        if value is None:
            return description, f"变量未定义: {var}"
        replaced = replaced.replace(match.group(0), str(value))
    return replaced, None


def execute_leaf(node: ActionNode | ConditionNode, ctx: LeafContext) -> LeafResult:
    """叶子统一执行入口（M6 spec §5.1）。

    :param node: Action 或 Condition 叶子节点（M2 解析产物）。
    :param ctx: 叶子执行上下文（LLM 配置 + M5 引擎 + 终止条件参数）。
    """
    node_type = _node_type(node)
    description, get_error = _resolve_get_refs(node.description, ctx)
    if get_error is not None:
        # 读取变量失败是程序错误：叶子直接 FAILURE（程序侧）
        return _build_leaf_result(
            node, node_type, _LeafOutcome("failure", None, "program", None, decision=get_error), ""
        )
    set_targets = tuple(getattr(node, "set_targets", ()))
    set_decls = tuple(getattr(node, "set_decls", ()))
    tools = ctx.tools if ctx.tools is not None else ENGINE_TOOLS
    system_prompt = build_system_prompt(node, schema_hint=_tool_names_text(tools))
    session = (ctx.session_factory or _default_session_factory(ctx))(ctx.config, system_prompt)

    try:
        graph_text = _fetch_initial_graph(ctx)
    except Exception as exc:
        return _build_leaf_result(node, node_type, _outcome_for_exception(exc), "")

    user_message = build_user_message(
        description=description,
        graph_text=graph_text,
        css_hint=_css_hint(node),
        set_targets=set_targets,
        set_decls=set_decls,
    )
    session.add_user_message(user_message)
    outcome = _run_agent_loop(session, ctx, node_type, tools, set_targets)
    return _build_leaf_result(node, node_type, outcome, graph_text)


def _run_agent_loop(
    session: LLMSession,
    ctx: LeafContext,
    node_type: Literal["action", "condition"],
    tools: list[ToolSpec],
    set_targets: tuple[str, ...] = (),
) -> _LeafOutcome:
    """agent 驱动循环：request → 工具调用回填 / 最终回答解析，直至终止。"""
    records: list[ToolCallRecord] = []
    reasoning: list[str] = []
    decision: str | None = None
    rounds = 0
    deadline = time.monotonic() + ctx.timeout if ctx.timeout is not None else None
    progress = NoProgressTracker(ctx.no_progress_rounds)
    try:
        while True:
            _check_deadline(deadline)
            response = session.request(tools=tools)
            if response.text:
                reasoning.append(response.text)
            if response.has_tool_calls:
                rounds += 1
                _check_round_limit(rounds, ctx.max_rounds)
                executed = _execute_tool_calls(
                    session, response.tool_calls, ctx, records, set_targets
                )
                if progress.record(_fingerprint(executed)):
                    raise LeafTermination("no_progress")
                _check_deadline(deadline)
                continue
            decision = response.text
            status, bool_value = parse_final_decision(decision, node_type)
            return _LeafOutcome(
                status=status,
                bool_value=bool_value,
                error_source=_error_source_for(node_type, status, bool_value),
                decision=decision,
                reasoning=reasoning,
                records=records,
            )
    except LeafTermination as term:
        return _LeafOutcome("failure", None, "llm", term.terminator, decision, reasoning, records)
    except DecisionError:
        return _LeafOutcome("failure", None, "llm", None, decision, reasoning, records)
    except Exception as exc:
        outcome = _outcome_for_exception(exc)
        return _LeafOutcome(
            status=outcome.status,
            bool_value=None,
            error_source=outcome.error_source,
            terminator=outcome.terminator,
            decision=decision,
            reasoning=reasoning,
            records=records,
        )


def _execute_tool_calls(
    session: LLMSession,
    tool_calls: list,
    ctx: LeafContext,
    records: list[ToolCallRecord],
    set_targets: tuple[str, ...] = (),
) -> list[tuple[str, str, str]]:
    """执行一轮全部工具调用并回填会话；返回指纹素材（函数名/参数/结果）。"""
    executed: list[tuple[str, str, str]] = []
    for call in tool_calls:
        name = call.name
        arguments = _safe_load_arguments(call.arguments)
        declared = {_norm_path(t) for t in set_targets}
        # 写变量类函数（extract 必须声明目标；open/get_url 带 save_to 时也须声明）
        if name == "extract":
            write_target = (arguments or {}).get("target")
            allowed = bool(set_targets) and _norm_path(write_target) in declared
            if not allowed:
                op = OpResult(
                    False,
                    f"extract 目标 {write_target!r} 未在叶子可写变量集内"
                    f"（声明: {', '.join(set_targets) or '无'}；请用 [[set:...]] 声明）",
                    {"code": "INVALID_ARGUMENT", "allowed": list(set_targets)},
                )
            else:
                if isinstance(arguments, dict) and _norm_path(write_target) != write_target:
                    arguments = {**arguments, "target": _norm_path(write_target)}
                op = ctx.engine.call(name, arguments)
        elif name in ("open", "get_url"):
            write_target = (arguments or {}).get("save_to")
            if write_target is None:
                op = ctx.engine.call(name, arguments)  # 无 save_to：open 默认活动页合法
            elif set_targets and _norm_path(write_target) in declared:
                if isinstance(arguments, dict) and _norm_path(write_target) != write_target:
                    arguments = {**arguments, "save_to": _norm_path(write_target)}
                op = ctx.engine.call(name, arguments)
            else:
                op = OpResult(
                    False,
                    f"{name} 目标 {write_target!r} 未在叶子可写变量集内"
                    f"（声明: {', '.join(set_targets) or '无'}；请用 [[set:...]] 声明）",
                    {"code": "INVALID_ARGUMENT", "allowed": list(set_targets)},
                )
        else:
            op = ctx.engine.call(name, arguments)
        result_text = _op_text(op)
        session.add_tool_result(call.id, ToolResult(call_id=call.id, content=result_text))
        records.append(
            ToolCallRecord(
                name=name,
                arguments=arguments,
                result=result_text,
                success=op.ok,
                timestamp=time.time(),
            )
        )
        executed.append(
            (name, json.dumps(arguments, sort_keys=True, ensure_ascii=False), result_text)
        )
    return executed


def _fetch_initial_graph(ctx: LeafContext) -> str:
    """获取初始语义图正文；失败返回说明（供 LLM 自行决策）。

    无当前页面（首次打开）是正常初始状态，返回明确引导而非报错：本动作
    若是访问/打开网址应直接 ``open``，无需先有当前页面。
    """
    op = ctx.engine.call(
        "semantic_graph",
        {"scope": ctx.initial_graph_scope, "lod": ctx.initial_graph_lod},
    )
    if not op.ok:
        error = op.error or "未知错误"
        if "无当前页面" in error:
            return (
                "（当前无打开的页面。若本动作是访问/打开某网址，请直接调用 open(url) 打开新页面，"
                "无需先有当前页面；若引用已保存的 url 字符串或页签变量，据此用 open 或 activate "
                "访问/切换已打开页面）"
            )
        return f"（初始语义图获取失败: {error}）"
    detail = op.detail or {}
    text = detail.get("text")
    if text:
        return str(text)
    return "(当前页面语义图为空)"


def _outcome_for_exception(exc: Exception) -> _LeafOutcome:
    """错误源分流（契约 §9.4）：致命/连接/超时 → 程序侧，其余 → LLM 侧。"""
    if isinstance(exc, FatalBrowserError):
        return _LeafOutcome("failure", None, "program", "fatal_error")
    if isinstance(exc, LLMConnectionError):
        return _LeafOutcome("failure", None, "program", "llm_connection")
    if isinstance(exc, LLMTimeoutError):
        return _LeafOutcome("failure", None, "program", "llm_timeout")
    if isinstance(exc, LLMBudgetExceeded):
        return _LeafOutcome("failure", None, "llm", "budget")
    if isinstance(exc, LLMError):
        return _LeafOutcome("failure", None, "llm", "llm_error")
    raise exc


def _error_source_for(
    node_type: str,
    status: Literal["success", "failure"],
    bool_value: bool | None,
) -> Literal["llm", "program"] | None:
    """错误来源默认分类：成功与 Condition 确定判断为 None，其余失败为 llm。"""
    if status == "success":
        return None
    if node_type == "condition" and bool_value is not None:
        return None
    return "llm"


def _build_leaf_result(
    node: ActionNode | ConditionNode,
    node_type: str,
    outcome: _LeafOutcome,
    graph_text: str,
) -> LeafResult:
    trace = LeafTrace(
        llm_input={
            "node_type": node_type,
            "description": node.description,
            "css_hint": _css_hint(node),
            "graph": graph_text,
            "prompt_version": PROMPT_VERSION,
        },
        llm_reasoning=list(outcome.reasoning),
        decision=outcome.decision,
        calls=[record.to_m8() for record in outcome.records],
        terminator=outcome.terminator,
    )
    return LeafResult(
        status=outcome.status,
        bool_value=outcome.bool_value,
        error_source=outcome.error_source,
        trace=trace,
    )


def _node_type(node: ActionNode | ConditionNode) -> Literal["action", "condition"]:
    if isinstance(node, ActionNode):
        return "action"
    if isinstance(node, ConditionNode):
        return "condition"
    raise TypeError(f"execute_leaf 仅支持 ActionNode/ConditionNode，收到 {type(node).__name__}")


def _default_session_factory(ctx: LeafContext):
    """默认会话工厂：按 ``config`` 构建真实会话（单次请求超时按 ctx 配置）。"""

    def _factory(config, system_prompt: str) -> LLMSession:
        return LLMSession(config=config, system_prompt=system_prompt, timeout=ctx.session_timeout)

    return _factory


def _tool_names_text(tools: list[ToolSpec]) -> str:
    names = ", ".join(tool.name for tool in tools)
    return f"可用引擎函数: {names}"


def _css_hint(node: ActionNode | ConditionNode) -> str | None:
    return node.css_hint if isinstance(node, ActionNode) else None


def _op_text(op: OpResult) -> str:
    """把 ``OpResult`` 转为回传 LLM 的可读工具结果文本。"""
    detail = op.detail or {}
    if not op.ok:
        code = detail.get("code")
        code_suffix = f" [code={code}]" if code else ""
        return f"失败{code_suffix}: {op.error or '未知错误'}"
    text = detail.get("text")
    if text:
        return f"成功（语义图）\n{text}"
    safe = {k: v for k, v in detail.items() if _is_jsonable(v)}
    suffix = json.dumps(safe, ensure_ascii=False) if safe else ""
    return "成功" if not suffix else f"成功\n{suffix}"


def _is_jsonable(value: Any) -> bool:
    try:
        json.dumps(value, ensure_ascii=False)
        return True
    except (TypeError, ValueError):
        return False


def _safe_load_arguments(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _fingerprint(executed: list[tuple[str, str, str]]) -> str:
    return json.dumps(executed, ensure_ascii=False, sort_keys=True)


def _check_deadline(deadline: float | None) -> None:
    if deadline is not None and time.monotonic() >= deadline:
        raise LeafTermination("timeout")


def _check_round_limit(rounds: int, max_rounds: int) -> None:
    if rounds > max_rounds:
        raise LeafTermination("round_limit")


__all__ = ["execute_leaf"]
