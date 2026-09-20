"""M6 叶子 agent 执行器（M6 spec §5.2、契约 §5.7.2/§5.7.2.1）。

``execute_leaf(node, ctx)`` 以 agent 式驱动单个叶子节点执行（插件模式）：

1. 构建 M0 会话（系统提示词 + 能力概览 + ``use_capability``）并注入用户消息
   （节点描述；无语义图预取）。
2. 循环：``session.request(当前工具集)`` → 含工具调用则经 M3 插件框架分发
   （``registry.call``）——``use_capability`` 加载插件并追加其函数进工具集；
   插件函数返回值，产出型工具由引擎落笔写变量 → 结果回填 → 直到模型返回
   纯文本（最终回答）或触发引擎兜底终止条件。
3. 最终回答解析为 Action 的 ``status`` / Condition 的 ``bool_value``。
4. 错误边界（§5.7.2.1/§9.4）：函数失败（``FunctionResult(ok=False)``）回传 LLM
   由其自行修正；``FatalBrowserError`` 终止整个流程；``LLMConnectionError`` /
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

from autobranch.browser import FatalBrowserError
from autobranch.leaf_agent.models import LeafContext, LeafResult, ToolCallRecord
from autobranch.leaf_agent.prompts import (
    PROMPT_VERSION,
    DecisionError,
    build_system_prompt,
    build_user_message,
    parse_final_decision,
)
from autobranch.leaf_agent.terminator import LeafTermination, NoProgressTracker
from autobranch.llm import (
    LLMBudgetExceeded,
    LLMConnectionError,
    LLMError,
    LLMProtocolError,
    LLMSession,
    LLMTimeoutError,
    ToolResult,
    ToolSpec,
)
from autobranch.parser.models import ActionNode, ConditionNode
from autobranch.plugin_system import FunctionResult
from autobranch.plugin_system.capability import (
    USE_CAPABILITY_TOOL,
    capability_overview,
    handle_use_capability,
)
from autobranch.reporting.models import LeafTrace
from autobranch.schema.errors import SchemaError
from autobranch.schema.types import coerce, infer_type


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
    screenshots: list[str] = field(default_factory=list)


#: ``Param.<name>`` 读取引用（叶子执行前程序替换；与 M2 同款正则，ASCII 词边界）
_GET_TMPL = re.compile(r"(?<![A-Za-z0-9_])Param\.([A-Za-z_][A-Za-z0-9_]*)")
#: 反引号转义段（`` `Param` `` → 纯文本，不替换）
_BACKTICK = re.compile(r"`([^`]*)`")


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
    """叶子执行前把 ``Param.x`` 替换为 blackboard 真实值（确定性）。

    返回 ``(替换后文本, None)``；读取失败（变量未定义）返回
    ``(原文, 错误说明)``——该叶子应直接 FAILURE，不让 LLM 猜测。
    反引号转义段（`` `Param.x` ``）不替换，并去除反引号。
    描述不含 ``Param.`` 时不做替换（即使未注入 space 也正常执行）。
    """
    if not _GET_TMPL.search(_BACKTICK.sub("", description)):
        return _BACKTICK.sub(r"\1", description), None
    if ctx.space is None:
        return description, "变量读取依赖 SchemaSpace（未注入 space）"
    frame = ctx.space._current
    parts = _BACKTICK.split(description)
    out: list[str] = []
    for idx, seg in enumerate(parts):
        if idx % 2 == 1:
            out.append(seg)
            continue
        replaced = seg
        for match in _GET_TMPL.finditer(seg):
            var = match.group(1)
            try:
                value = ctx.space.read(frame, var)
            except SchemaError as exc:
                return description, f"变量读取失败（{var}）: {exc}"
            if value is None:
                return description, f"变量未定义: {var}"
            replaced = replaced.replace(match.group(0), str(value))
        out.append(replaced)
    return "".join(out), None


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
            node,
            node_type,
            _LeafOutcome("failure", None, "program", None, decision=get_error),
            "",
            resolved_description=description,
        )
    set_targets = tuple(getattr(node, "set_targets", ()))
    set_decls = tuple(getattr(node, "set_decls", ()))
    tools = ctx.tools if ctx.tools is not None else _initial_tools(ctx)
    system_prompt = build_system_prompt(node, schema_hint=_tool_names_text(tools))
    if ctx.registry is not None:
        system_prompt += f"\n\n{capability_overview(ctx.registry)}"
    session = (ctx.session_factory or _default_session_factory(ctx))(ctx.config, system_prompt)

    # 经验回灌：替换 Param 后按节点身份查历史成功经验（三钥匙匹配），命中才注入
    reference = None
    if ctx.experience_lookup is not None:
        reference = ctx.experience_lookup(description)
    graph_text = ""
    user_message = build_user_message(
        description=description,
        graph_text=graph_text,
        css_hint=_css_hint(node),
        set_targets=set_targets,
        set_decls=set_decls,
        reference=reference,
    )
    session.add_user_message(user_message)
    outcome = _run_agent_loop(session, ctx, node_type, tools, set_targets, set_decls)
    return _build_leaf_result(
        node, node_type, outcome, graph_text, resolved_description=description
    )


def _run_agent_loop(
    session: LLMSession,
    ctx: LeafContext,
    node_type: Literal["action", "condition"],
    tools: list[ToolSpec],
    set_targets: tuple[str, ...] = (),
    set_decls: tuple[tuple[str, str], ...] = (),
) -> _LeafOutcome:
    """agent 驱动循环：request → 工具调用回填 / 最终回答解析，直至终止。

    工具集动态增长（``use_capability`` 追加插件函数）。
    """
    records: list[ToolCallRecord] = []
    reasoning: list[str] = []
    decision: str | None = None
    screenshots: list[str] = []
    rounds = 0
    current_tools = list(tools)
    deadline = time.monotonic() + ctx.timeout if ctx.timeout is not None else None
    progress = NoProgressTracker(ctx.no_progress_rounds)
    try:
        while True:
            _check_deadline(deadline)
            try:
                response = session.request(tools=current_tools)
            except LLMProtocolError as exc:
                # LLM 输出畸形（工具参数非合法 JSON / 响应不可解析）：回填纠错指令，预算内重试
                rounds += 1
                _check_round_limit(rounds, ctx.max_rounds)
                session.add_user_message(
                    f"上一轮 LLM 输出无法解析（{exc}）。请重新输出规范的工具调用，"
                    "工具调用参数必须是合法 JSON；不要重复输出已执行的调用。"
                )
                progress.record(_fingerprint([("__llm_retry__", str(exc), "")]))
                continue
            if response.text:
                reasoning.append(response.text)
            if response.has_tool_calls:
                rounds += 1
                _check_round_limit(rounds, ctx.max_rounds)
                executed, added, new_shots = _execute_tool_calls(
                    session,
                    response.tool_calls,
                    ctx,
                    records,
                    set_targets,
                    current_tools,
                    set_decls,
                )
                if added:
                    current_tools.extend(added)
                if new_shots:
                    screenshots.extend(new_shots)
                if progress.record(_fingerprint(executed)):
                    raise LeafTermination("no_progress")
                _check_deadline(deadline)
                continue
            decision = response.text
            try:
                status, bool_value = parse_final_decision(decision, node_type)
            except DecisionError as exc:
                # 最终回答不可解析：回填纠错指令，预算内重试
                rounds += 1
                _check_round_limit(rounds, ctx.max_rounds)
                session.add_user_message(
                    f"无法解析最终结果（{exc}）。请以「结果: 成功」或「结果: 失败」"
                    "（Condition 为「结果: 真」/「结果: 假」）的格式重新输出最终结论。"
                )
                progress.record(_fingerprint([("__decision_retry__", str(exc), "")]))
                continue
            return _LeafOutcome(
                status=status,
                bool_value=bool_value,
                error_source=_error_source_for(node_type, status, bool_value),
                decision=decision,
                reasoning=reasoning,
                records=records,
                screenshots=screenshots,
            )
    except LeafTermination as term:
        return _LeafOutcome(
            "failure", None, "llm", term.terminator, decision, reasoning, records, screenshots
        )
    except DecisionError:
        return _LeafOutcome(
            "failure", None, "llm", None, decision, reasoning, records, screenshots
        )
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
            screenshots=screenshots,
        )


def _execute_tool_calls(
    session: LLMSession,
    tool_calls: list,
    ctx: LeafContext,
    records: list[ToolCallRecord],
    set_targets: tuple[str, ...] = (),
    current_tools: list[ToolSpec] | None = None,
    set_decls: tuple[tuple[str, str], ...] = (),
) -> tuple[list[tuple[str, str, str]], list[ToolSpec], list[str]]:
    """执行一轮全部工具调用并回填会话；返回指纹素材与新增工具（插件模式）。

    插件模式（``ctx.registry`` 非空）下处理 ``use_capability`` 与插件函数
    （产出型工具由引擎落笔写变量）；否则走旧引擎路径。
    """
    executed: list[tuple[str, str, str]] = []
    added: list[ToolSpec] = []
    screenshots: list[str] = []
    for call in tool_calls:
        name = call.name
        arguments = _safe_load_arguments(call.arguments)
        op, result_text, new_tools, shot = _plugin_tool_call(
            ctx, name, arguments, set_targets, set_decls
        )
        if new_tools:
            added.extend(new_tools)
        if shot:
            screenshots.append(shot)
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
    return executed, added, screenshots


def _plugin_tool_call(
    ctx: LeafContext,
    name: str,
    arguments: dict,
    set_targets: tuple[str, ...],
    set_decls: tuple[tuple[str, str], ...] = (),
) -> tuple[FunctionResult, str, list[ToolSpec], str | None]:
    """插件路径：use_capability / 插件函数分发（产出型落笔）。

    返回 ``(result, text, new_tools, screenshot)``；``screenshot`` 为
    semantic_graph 调用产生的截图路径（供叶子报告展示）。
    """
    if name == "use_capability":
        result = handle_use_capability(ctx.registry, arguments, runtime=ctx.runtime)
        new_tools = list(result.detail.get("functions", [])) if result.ok else []
        return result, _plugin_text(result, "plugin-system"), new_tools, None
    spec = ctx.registry.function(name)
    full_name = name
    if spec is None:
        # LLM 工具名经 ``.`` → ``__`` 转义：按 tool_name 反查回全名分发
        for candidate in ctx.registry.loaded_functions():
            if candidate.tool_name == name:
                spec, full_name = candidate, candidate.full_name
                break
    if spec is None:
        result = FunctionResult.failure(
            f"未知函数: {name}（函数未注册，请先 use_capability 加载对应能力）"
        )
        return result, _plugin_text(result, ""), [], None
    if spec.is_producing:
        target = (arguments or {}).get(spec.output_param)
        declared = {_norm_path(t) for t in set_targets}
        call_args = {k: v for k, v in (arguments or {}).items() if k != spec.output_param}
        if not target:
            # 未提供目标 → 不落笔（可选产出，如 open 无 save_to）
            result = ctx.registry.call(full_name, call_args, runtime=ctx.runtime)
            return result, _plugin_text(result, ctx.registry.owner(full_name) or ""), [], None
        if _norm_path(target) not in declared:
            result = FunctionResult.failure(
                f"{full_name} 目标 {target!r} 未在叶子可写变量集内"
                f"（声明: {', '.join(set_targets) or '无'}；请用 NewParam.x 声明）"
            )
            return result, _plugin_text(result, ""), [], None
        result = ctx.registry.call(full_name, call_args, runtime=ctx.runtime)
        if result.ok:
            decl_type = dict(set_decls).get(_norm_path(target), "")
            _write_result(ctx, _norm_path(target), result.value, decl_type)
    else:
        result = ctx.registry.call(full_name, arguments, runtime=ctx.runtime)
    owner = ctx.registry.owner(full_name) or ""
    screenshot = None
    if spec.name == "semantic_graph" and result.ok:
        screenshot = (result.detail or {}).get("screenshot")
    return result, _plugin_text(result, owner), [], screenshot


def _initial_tools(ctx: LeafContext) -> list[ToolSpec]:
    """插件模式初始工具集：能力框架工具 + 已加载插件的函数。"""
    tools = [USE_CAPABILITY_TOOL]
    for spec in ctx.registry.loaded_functions():
        extra = None
        if spec.is_producing:
            extra = {
                spec.output_param: {
                    "type": "string",
                    "description": "产出值存入的变量名（裸名，须在 NewParam. 声明集内）",
                }
            }
        tools.append(spec.to_tool_spec(extra_params=extra))
    return tools


def _write_result(ctx: LeafContext, target: str, value: Any, type_name: str = "") -> None:
    """引擎落笔：把产出型工具返回值写入当前帧目标变量。

    ``type_name`` 来自节点 ``NewParam.名[:类型]`` 声明；声明为具体类型（如 int）
    时先 coerce 再存（网页提取值默认 str）。
    """
    if ctx.space is None:
        return
    frame = getattr(ctx.space, "_current", None)
    if frame is None:
        return
    try:
        stored = coerce(type_name, value) if type_name else value
        ctx.space.write(frame, f"this/{target}", stored, type_name or infer_type(value))
    except Exception:  # noqa: BLE001 - 落笔失败不阻断 agent（工具结果已回传）
        pass


def _plugin_text(result: FunctionResult, plugin_name: str = "") -> str:
    """把 ``FunctionResult`` 转为回传 LLM 的可读文本（含报告附加信息）。"""
    if not result.ok:
        return f"失败: {result.error or '未知错误'}"
    parts: list[str] = []
    if result.values:
        parts.append(", ".join(str(v) for v in result.values))
    for sec in (result.report or {}).get("sections", []):
        title = sec.get("title", "")
        body = sec.get("body", "")
        parts.append(f"[{title}] {body}" if title else str(body))
    return "成功" if not parts else "成功\n" + "\n".join(parts)


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
    *,
    resolved_description: str,
) -> LeafResult:
    trace = LeafTrace(
        llm_input={
            "node_type": node_type,
            "description": resolved_description,
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
        screenshots=tuple(outcome.screenshots),
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
