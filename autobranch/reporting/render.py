"""两份报告的文本渲染（M8 spec §5.2、契约 §5.8.3）。

- 报告① 执行情况报告：每节点类型/描述/结果/函数调用/判断结果/时间/URL/截图，
  不含 LLM 推理（``render_exec_report``）。
- 报告② 回溯报告：执行详情 + LLM 输入/推理过程/决策结果，不含任何截图字段
  （``render_trace_report``）。

两份报告均由同一组 ``NodeReport`` 派生（设计决策 3，单数据源），按节点执行
顺序组织，格式清晰可读、可直接展示或经 M9b 提供。

截图引用：执行报告的截图以 **Markdown 图片语法** 输出
（``![节点描述](相对文件名)``）。截图与 exec_report.md 同目录（M8 存储布局
``<report_dir>/<run_id>/``），故用相对文件名即可在 Markdown 预览中直接显示。
"""

from __future__ import annotations

import os
import re

from autobranch.reporting.models import ActionCall, LeafTrace, NodeReport

_SEP = "-" * 64
_DETAIL_LIMIT = 200

#: 用于 Markdown 图片 alt 文本清洗（反引号/换行等在图片语法中会破坏解析）。
_ALT_CLEAN_RE = re.compile(r"[`*_\[\]<>]")


def _result_label(result: str) -> str:
    return "SUCCESS" if result == "success" else "FAILURE"


def _summary(value: object, limit: int = _DETAIL_LIMIT) -> str:
    """报告辅助详情截断：超长标注完整长度，避免单行报告无限膨胀。"""
    text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}…（已截断，完整长度 {len(text)} 字符）"


def _action_call_line(call: ActionCall) -> str:
    status = "成功" if call.success else "失败"
    line = f"函数调用: {call.function}（{status}）"
    if call.arguments:
        line += f" 参数={_summary(call.arguments)}"
    if call.error:
        line += f" 错误={call.error}"
    return line


def _condition_line(value: bool) -> str:
    return f"判断结果: {'是' if value else '否'}（{value}）"


def _node_header(index: int, report: NodeReport) -> str:
    return f"[{index}] {report.node_type}｜{report.node_desc} → {_result_label(report.result)}"


def _common_detail_lines(report: NodeReport) -> list[str]:
    lines = [
        f"    节点类型: {report.node_type}",
        f"    节点 ID: {report.node_id or '-'}",
        f"    节点描述: {report.node_desc}",
        f"    结果: {_result_label(report.result)}",
    ]
    if report.duration is not None:
        lines.append(f"    耗时: {report.duration}s")
    if report.parallel:
        lines.append(f"    并行: {report.parallel}")
    if report.function:
        lines.append(f"    函数: {report.function}")
        args_text = _summary(report.arguments) if report.arguments is not None else "-"
        lines.append(f"    入参: {args_text}")
        if report.kwargs:
            lines.append(f"    命名参数: {_summary(report.kwargs)}")
        lines.append(f"    出参: {_summary(report.returns) if report.returns is not None else '-'}")
    else:
        if report.arguments is not None:
            lines.append(f"    入参: {_summary(report.arguments)}")
        if report.kwargs:
            lines.append(f"    命名参数: {_summary(report.kwargs)}")
        if report.returns is not None:
            lines.append(f"    出参: {_summary(report.returns)}")
    if report.details:
        lines.append(f"    详情: {_summary(report.details)}")
    if report.action_call is not None:
        lines.append(f"    {_action_call_line(report.action_call)}")
    if report.condition_result is not None:
        lines.append(f"    {_condition_line(report.condition_result)}")
    if report.failure_reason:
        lines.append("    失败原因:")
        for line in str(report.failure_reason).splitlines():
            lines.append(f"      {line}")
    lines.append(f"    时间: {report.timestamp}")
    lines.append(f"    URL: {report.page_url or '-'}")
    return lines


def _screenshot_md(report: NodeReport) -> str:
    """Markdown 图片引用：截图与报告同目录，用相对文件名；alt 用节点描述。"""
    filename = os.path.basename(report.screenshot_path)
    alt = _ALT_CLEAN_RE.sub("", report.node_desc) or "截图"
    return f"    截图: ![节点截图: {alt}]({filename})"


def render_exec_report(run_id: str, reports: list[NodeReport]) -> str:
    """报告①：每节点执行结果 + 截图，不含 LLM 推理内容。"""
    lines = ["# 执行情况报告", f"运行标识: {run_id}", f"节点数: {len(reports)}", _SEP]
    for index, report in enumerate(reports, start=1):
        lines.append(_node_header(index, report))
        lines.extend(_common_detail_lines(report))
        if report.screenshot_path:
            lines.append(_screenshot_md(report))
        lines.append(_SEP)
    return "\n".join(lines)


def _trace_lines(trace: LeafTrace, index: int, header: str) -> list[str]:
    sep = "=" * 64
    lines = [
        f"    {sep}",
        f"    LLM 推理过程 — 节点 [{index}] {header}",
        f"    {sep}",
        "    [输入] LLM 输入:",
    ]
    for key, value in trace.llm_input.items():
        lines.append(f"      {key}: {value}")
    lines.append("    LLM 推理过程:")
    if trace.llm_reasoning:
        for step in trace.llm_reasoning:
            lines.append(f"      - {step}")
    else:
        lines.append("      （无）")
    if trace.calls:
        lines.append("    [工具调用] 工具调用序列:")
        for call in trace.calls:
            outcome = "" if call.success is None else ("成功" if call.success else "失败")
            tail = f" → {call.result}" if call.result else ""
            lines.append(f"      - {call.name}（{outcome}）{tail}")
    if trace.decision:
        lines.append(f"    [决策] LLM 决策结果: {trace.decision}")
    if trace.terminator:
        lines.append(f"    终止条件: {trace.terminator}")
    lines.append(f"    {sep}")
    return lines


def render_trace_report(run_id: str, reports: list[NodeReport]) -> str:
    """报告②：执行详情 + LLM 推理，不含任何截图字段。"""
    lines = ["# 回溯报告", f"运行标识: {run_id}", f"节点数: {len(reports)}", _SEP]
    for index, report in enumerate(reports, start=1):
        header = _node_header(index, report)
        lines.append(header)
        lines.extend(_common_detail_lines(report))
        if report.llm_trace is not None:
            lines.extend(_trace_lines(report.llm_trace, index, header))
        lines.append(_SEP)
    return "\n".join(lines)
