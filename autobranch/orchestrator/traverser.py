"""M7 遍历器（design D1/D3/D4/D5/D6）：阻塞式 tick、组合节点聚合、ref 动态调用与报告。

遍历器把全部基础节点统一为 ``tick`` 契约（返回 SUCCESS/FAILURE，无 RUNNING）：
- 组合节点（Sequence/Selector/Repeat/Finish）纯程序执行、按 §5.7.7 聚合短路；
- 叶子（Action/Condition）触发 M6（经注入的叶子执行器），接收 ``LeafResult``；
- ref（``RefNode``）运行时动态调用：建子帧 → 注入实参 → 递归执行目标块树 →
  回收 returns 到父帧 → 退出子帧（帧由 ``_tick_ref`` 管理，无静态 frame 同步）；
- 每个节点退出前记录 M8 报告、叶子返回前截图（§5.8.3）；
- 维护可查询执行状态（Reporter 内）与递归深度安全闸（design R1）。
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from autobranch.browser.errors import FatalBrowserError
from autobranch.leaf_agent.models import LeafResult
from autobranch.orchestrator.context import RunContext
from autobranch.orchestrator.models import FAILURE, SUCCESS, NodeStatus, OrchestratorError
from autobranch.parser.models import (
    ActionNode,
    ConditionNode,
    DefineNode,
    FinishNode,
    ForEachNode,
    FunctionCallNode,
    Node,
    ParallelNode,
    PredicateCall,
    PredicateExpr,
    RefNode,
    RepeatNode,
    SelectorNode,
    SequenceNode,
)
from autobranch.plugin_system.defs import AUTOBRANCH_TYPE_KEY
from autobranch.reporting.models import ActionCall, LeafTrace, NodeInfo, NodeReport
from autobranch.schema import FrameDecl, SchemaSpace
from autobranch.schema.errors import SchemaError
from autobranch.schema.types import (
    TYPE_REGISTRY,
    check_type,
    coerce,
    infer_type,
    read_path_value,
)
from autobranch.timeutil import now_local_naive

logger = logging.getLogger(__name__)

#: 递归栈深度安全闸（design R1；M2 解析已有展开深度上限，此处作运行期兜底）。
_MAX_RECURSION_DEPTH = 512


def node_type_name(node: Node) -> str:
    """节点类型名（M8 报告用）。"""
    if isinstance(node, ActionNode):
        return "Action"
    if isinstance(node, ConditionNode):
        return "Condition"
    if isinstance(node, RefNode):
        return "Ref"
    if isinstance(node, FunctionCallNode):
        return "FunctionCall"
    if isinstance(node, DefineNode):
        return "Define"
    if isinstance(node, SequenceNode):
        return "Sequence"
    if isinstance(node, SelectorNode):
        return "Selector"
    if isinstance(node, RepeatNode):
        return "Repeat"
    if isinstance(node, ForEachNode):
        return "ForEach"
    if isinstance(node, ParallelNode):
        return "Parallel"
    if isinstance(node, FinishNode):
        return "Finish"
    return type(node).__name__


def _predicate_summary(expr: PredicateExpr | None) -> str:
    if expr is None:
        return "谓词条件"
    if isinstance(expr, PredicateCall):
        return f"{expr.function}({', '.join(str(arg) for arg in expr.args)})"
    return f"{expr.op.upper()}(" + ", ".join(_predicate_summary(c) for c in expr.children) + ")"


def node_desc(node: Node) -> str:
    """节点描述：叶子取自然语言描述，组合节点取类型名。"""
    if isinstance(node, ConditionNode) and node.mode == "predicate":
        return _predicate_summary(node.expression)
    if isinstance(node, (ActionNode, ConditionNode)):
        return node.description
    if isinstance(node, FunctionCallNode):
        return f"{node.function}({', '.join(str(arg) for arg in node.args)})"
    if isinstance(node, DefineNode):
        return f"Define({', '.join(name for name, _t, _v in node.vars)})"
    if isinstance(node, ForEachNode):
        return "ForEach(" + ", ".join(f"{name}={value}" for name, value in node.variables) + ")"
    if isinstance(node, ParallelNode):
        return "Parallel(" + ", ".join(f"{name}={value}" for name, value in node.variables) + ")"
    return node_type_name(node)


def count_nodes(
    node: Node,
    blocks_tree: dict[str, Node] | None = None,
    _seen: set[str] | None = None,
    resolver=None,
) -> int:
    """统计树中基础节点总数（供 ``ExecState.progress`` 计算，design D3）。

    ``RefNode`` 计 1，并递归计入其被引用文档树（经 resolver 加载；无
    resolver 时回退 ``blocks_tree``）。运行期 ``_tick_ref`` 递归 tick 被引
    文档并逐节点记录，故 total 必须同样计入，否则 completed/total 提前
    超 1、进度饱和到 1.0。ref 图静态已保证 DAG，此处 ``_seen`` 作防御性
    环保护。
    """
    total = 1
    if isinstance(node, RefNode):
        target = (node.ref_target or "").strip()
        child = None
        if target and "/" not in target:
            if resolver is not None:
                child = _load_doc_tree_for_count(resolver, target)
            elif blocks_tree is not None:
                child = blocks_tree.get(target)
        if child is not None:
            key = target
            if _seen is None:
                _seen = set()
            if key not in _seen:
                _seen.add(key)
                total += count_nodes(child, blocks_tree, _seen, resolver)
    elif isinstance(node, SequenceNode):
        for child in node.children:
            total += count_nodes(child, blocks_tree, _seen, resolver)
    elif isinstance(node, SelectorNode):
        for branch in node.branches:
            if branch.condition is not None:
                total += count_nodes(branch.condition, blocks_tree, _seen, resolver)
            total += count_nodes(branch.child, blocks_tree, _seen, resolver)
    elif isinstance(node, RepeatNode):
        if node.until is not None:
            total += count_nodes(node.until, blocks_tree, _seen, resolver)
        total += count_nodes(node.body, blocks_tree, _seen, resolver)
    return total


def _load_doc_tree_for_count(resolver, doc_id: str):
    """经 resolver 加载被引文档并展开其主树（仅进度计数用，不执行）。"""
    try:
        from autobranch.parser.expand import ExpandContext, expand_document
        from autobranch.parser.onedoc import parse_document as parse_onedoc

        src = resolver.resolve(doc_id)
        ores = parse_onedoc(src, resolver)
        if not ores.checks_ok() or ores.main_tree is None:
            return None
        ectx = ExpandContext(max_depth=64)
        return expand_document(ores.main_tree, ectx, decl_inputs=ores.decl_inputs).tree
    except Exception:
        return None


def _now_iso() -> str:
    return now_local_naive().isoformat(timespec="seconds")


class Traverser:
    """确定性阻塞式遍历器（契约 §5.7.7）。

    :param ctx: 运行上下文（依赖注入，mock 友好）。
    """

    def __init__(self, ctx: RunContext) -> None:
        self.ctx = ctx
        self._depth = 0
        self._foreach_seq = 0
        self._parallel_seq = 0
        self._meta_stack: list[dict] = []
        self._predicate_error: str | None = None

    # ------------------------------------------------------------ tick 契约

    def tick(self, node: Node) -> NodeStatus:
        """节点统一 tick：返回 SUCCESS/FAILURE（阻塞式，无 RUNNING）。

        帧由运行时动态管理：``RefNode`` 经 ``_tick_ref`` 建子帧/退出子帧；
        其余节点共享所在块帧，不做帧切换。运行期 ``SchemaError`` 捕获后按失败
        沿树传播（§5.7.7）；致命错误（``FatalBrowserError``）原样上抛。
        """
        self._check_depth()
        self._depth += 1
        started = time.monotonic()
        self._meta_stack.append({})
        self._start_node(node)
        status: NodeStatus = FAILURE
        try:
            try:
                status = self._dispatch(node)
            except SchemaError as exc:
                self._note_failure(node, f"运行期 schema 错误: {exc}")
                status = FAILURE
        finally:
            meta = self._meta_stack.pop()
            if not isinstance(node, (ActionNode, ConditionNode)):
                self._record_node(node, status, meta, started)
            self._depth -= 1
        return status

    # ------------------------------------------------------------ 节点分派

    def _dispatch(self, node: Node) -> NodeStatus:
        if isinstance(node, RefNode):
            return self._tick_ref(node)
        if isinstance(node, FunctionCallNode):
            return self._tick_function_call(node)
        if isinstance(node, DefineNode):
            return self._tick_define(node)
        if isinstance(node, ConditionNode) and node.mode == "predicate":
            return self._tick_predicate_condition(node)
        if isinstance(node, (ActionNode, ConditionNode)):
            return self._tick_leaf(node)
        if isinstance(node, SequenceNode):
            return self._tick_sequence(node)
        if isinstance(node, SelectorNode):
            return self._tick_selector(node)
        if isinstance(node, RepeatNode):
            return self._tick_repeat(node)
        if isinstance(node, ForEachNode):
            return self._tick_for_each(node)
        if isinstance(node, ParallelNode):
            return self._tick_parallel(node)
        if isinstance(node, FinishNode):
            return self._tick_finish(node)
        self._note_failure(node, f"未知节点类型: {type(node).__name__}")
        logger.warning("未知节点类型 %s", type(node).__name__)
        return FAILURE

    def _tick_sequence(self, node: SequenceNode) -> NodeStatus:
        """Sequence：依次执行，首个 FAILURE 短路 → 整体 FAILURE；全 SUCCESS → SUCCESS。"""
        for child in node.children:
            if self.tick(child) == FAILURE:
                return FAILURE
        return SUCCESS

    def _tick_selector(self, node: SelectorNode) -> NodeStatus:
        """Selector：按条件分流，首个命中分支生效（短路）；全 FAILURE → FAILURE。

        分支条件（``condition``）先判：FAILURE 则试下一分支；SUCCESS（或
        otherwise 无条件分支）即执行该分支子节点，其结果即 Selector 结果
        （不承载兜底，命中后不再检查其余分支）。
        """
        for branch in node.branches:
            if branch.condition is not None:
                self._predicate_error = None
                cond_status = self.tick(branch.condition)
                if self._predicate_error is not None:
                    return FAILURE
                if cond_status == FAILURE:
                    continue
            return self.tick(branch.child)
        return FAILURE

    def _tick_repeat(self, node: RepeatNode) -> NodeStatus:
        """Repeat：循环带上限；到达上限仍未满足退出条件 → 整体 FAILURE。"""
        if node.max <= 0:
            return FAILURE
        if node.mode == "loop_until":
            return self._tick_loop_until(node)
        return self._tick_retry(node)

    def _tick_loop_until(self, node: RepeatNode) -> NodeStatus:
        """LoopUntil：每轮先判 until（页面条件），满足即退；不满足才执行 body。"""
        for _ in range(node.max):
            if node.until is None:
                self._note_failure(node, "loop_until 缺少 until 条件")
                return FAILURE
            self._predicate_error = None
            until_status = self.tick(node.until)
            if self._predicate_error is not None:
                return FAILURE
            if until_status == SUCCESS:
                return SUCCESS
            if self.tick(node.body) == FAILURE:
                return FAILURE
        return FAILURE

    def _tick_retry(self, node: RepeatNode) -> NodeStatus:
        """Retry：每轮直接执行 body，成功即退；失败重试至 max 上界。"""
        for _ in range(node.max):
            if self.tick(node.body) == SUCCESS:
                return SUCCESS
        return FAILURE

    def _tick_for_each(self, node: ForEachNode) -> NodeStatus:
        """ForEach：解析变量列表，逐项在临时子帧执行 body。

        子帧复用同一作用域，便于子树用 collect 类函数跨迭代累积结果；
        item 变量在循环结束后随子帧移除，对外部不可见。
        """
        space = self.ctx.space
        if node.body is None:
            self._note_failure(node, "ForEach 缺少 body 子节点")
            return FAILURE
        values: dict[str, object] = {}
        list_names: list[str] = []
        lengths: set[int] = set()
        for name, raw in node.variables:
            value = raw
            if isinstance(raw, str):
                evaluated = self._eval_arg(self.ctx.current_frame, raw)
                if evaluated is not _MISSING:
                    value = evaluated
                elif _PARAM_REF.match(raw.strip()):
                    self._note_failure(node, f"ForEach 变量 '{name}' 引用的变量未定义")
                    return FAILURE
            parsed = self._as_foreach_list(value)
            values[name] = parsed if parsed is not None else value
            if parsed is not None:
                list_names.append(name)
                lengths.add(len(parsed))
        if len(lengths) > 1:
            self._note_failure(node, f"ForEach 列表变量长度不一致: {sorted(lengths)}")
            return FAILURE
        count = next(iter(lengths)) if lengths else 1
        if count == 0:
            return SUCCESS

        frame = None
        self._foreach_seq += 1
        frame_name = f"ForEach#{self._foreach_seq}"
        parent = self.ctx.current_frame
        previous_failure = self.ctx.failure_reason
        first_failure: str | None = None
        failed_iterations = 0
        meta = self._meta_stack[-1] if self._meta_stack else {}
        meta["details"] = {
            "变量": {name: self._value_summary(value) for name, value in values.items()},
            "迭代次数": count,
        }
        try:
            frame = space.enter_frame(frame_name, mount=parent)
            for index in range(count):
                for name, value in values.items():
                    item = value[index] if name in list_names else value
                    value_type = (
                        "generics"
                        if item is None
                        else "array"
                        if isinstance(item, list)
                        else "object"
                        if isinstance(item, dict)
                        else infer_type(item)
                    )
                    space.write(frame, f"this/{name}", item, value_type)
                status = self.tick(node.body)
                if status == FAILURE:
                    failed_iterations += 1
                    meta["details"]["失败迭代数"] = failed_iterations
                    if first_failure is None:
                        first_failure = self.ctx.failure_reason
                    if node.on_failure == "abort":
                        return FAILURE
                    self.ctx.failure_reason = previous_failure
                    continue
                # 把 body 写入的非 item 变量回写父帧（支持 transform.append 累积结果）。
                for name in list(frame.storage):
                    if name in values:
                        continue
                    value = frame.storage[name]
                    space.write(
                        parent,
                        f"this/{name}",
                        value,
                        frame.declared.get(name) or infer_type(value),
                    )
                if node.break_on_success:
                    meta["details"]["提前终止"] = index + 1
                    break
        finally:
            if frame is not None:
                space.exit_frame(frame)
                if parent is not None:
                    parent.children.pop(frame_name, None)
        if failed_iterations == count:
            meta["details"]["全部失败"] = True
            if first_failure is not None:
                self.ctx.failure_reason = first_failure
            else:
                self._note_failure(node, f"全部 {count} 轮执行失败")
            return FAILURE
        return SUCCESS

    @staticmethod
    def _copy_parallel_value(value: object) -> object:
        """并行工作副本：仅递归复制基础容器，PageRef/插件对象共享引用。"""
        if isinstance(value, dict):
            return {
                key: Traverser._copy_parallel_value(item) for key, item in value.items()
            }
        if isinstance(value, list):
            return [Traverser._copy_parallel_value(item) for item in value]
        if isinstance(value, tuple):
            return tuple(Traverser._copy_parallel_value(item) for item in value)
        return value

    @staticmethod
    def _parallel_values_equal(left: object, right: object) -> bool:
        try:
            return bool(left == right)
        except Exception:  # noqa: BLE001 - 自定义对象比较失败时按身份判断
            return left is right

    @staticmethod
    def _merge_config_chain(frame):
        """收集帧配置继承链（当前帧优先），供并行工作空间复用。"""
        chain = []
        node = frame
        while node is not None:
            chain.append(node)
            node = node.config_parent
        config: dict[str, object] = {}
        config_types: dict[str, str] = {}
        for item in reversed(chain):
            config.update(item.config)
            config_types.update(item.config_types)
        return config, config_types

    def _make_parallel_context(
        self,
        parent,
        values: dict[str, object],
        list_names: list[str],
        index: int,
        label: str,
    ):
        """创建单次并行迭代的隔离上下文与帧。"""
        config, config_types = self._merge_config_chain(parent)
        worker_space = SchemaSpace(global_config=config, global_config_types=config_types)
        frame = worker_space.enter_frame(parent.name, mount=worker_space.root)
        frame.inputs = dict(parent.inputs)
        frame.outputs = dict(parent.outputs)
        for name, value in parent.storage.items():
            worker_space.write(
                frame,
                f"this/{name}",
                self._copy_parallel_value(value),
                parent.declared.get(name) or infer_type(value),
            )
        frame.page_write_order = list(parent.page_write_order)
        for name, value in values.items():
            item = value[index] if name in list_names else value
            value_type = (
                "generics"
                if item is None
                else "array"
                if isinstance(item, list)
                else "object"
                if isinstance(item, dict)
                else infer_type(item)
            )
            worker_space.write(frame, f"this/{name}", self._copy_parallel_value(item), value_type)
        factory = self.ctx.leaf_executor_factory
        leaf_executor = factory(worker_space) if factory is not None else self.ctx.leaf_executor
        worker_ctx = RunContext(
            config=self.ctx.config,
            space=worker_space,
            reporter=self.ctx.reporter,
            browser=self.ctx.browser,
            leaf_executor=leaf_executor,
            blocks_tree=self.ctx.blocks_tree,
            resolver=self.ctx.resolver,
            decl_inputs=self.ctx.decl_inputs,
            decl_outputs=self.ctx.decl_outputs,
            config_overrides=self.ctx.config_overrides,
            registry=self.ctx.registry,
            runtime=self.ctx.runtime,
            parallel_label=label,
            leaf_executor_factory=self.ctx.leaf_executor_factory,
            resolver_lock=self.ctx.resolver_lock,
        )
        return worker_ctx, frame

    def _parallel_changes(
        self, frame, seed: dict[str, object], item_names: set[str]
    ) -> dict[str, tuple[object, str]]:
        changes: dict[str, tuple[object, str]] = {}
        for name, value in frame.storage.items():
            if name in item_names:
                continue
            if name not in seed or not self._parallel_values_equal(value, seed[name]):
                changes[name] = (value, frame.declared.get(name) or infer_type(value))
        return changes

    def _merge_parallel_changes(
        self,
        parent,
        successes: list[dict],
        item_names: set[str],
        on_conflict: str,
    ) -> tuple[list[str], str | None]:
        """把成功迭代的变量写入父帧；返回冲突变量与冲突错误。"""
        by_name: dict[str, list[tuple[int, object, str]]] = {}
        for result in successes:
            for name, (value, value_type) in result["changes"].items():
                if name in item_names:
                    continue
                by_name.setdefault(name, []).append((result["index"], value, value_type))
        conflicts: list[str] = []
        for name, entries in by_name.items():
            first = entries[0][1]
            if any(not self._parallel_values_equal(first, value) for _, value, _ in entries[1:]):
                conflicts.append(name)
        for name, entries in by_name.items():
            if name in conflicts and on_conflict == "error":
                continue
            last = max(entries, key=lambda item: item[0])
            try:
                self.ctx.space.write(parent, f"this/{name}", last[1], last[2])
            except SchemaError as exc:
                return conflicts, f"并行变量回写 '{name}' 失败: {exc}"
        if conflicts and on_conflict == "error":
            return conflicts, f"并行变量写冲突: {', '.join(conflicts)}（可设置 on_conflict=last）"
        return conflicts, None

    def _tick_parallel(self, node: ParallelNode) -> NodeStatus:
        """Parallel：按列表逐项并发执行 body；每项使用隔离变量空间。"""
        if node.body is None:
            self._note_failure(node, "Parallel 缺少 body 子节点")
            return FAILURE
        values: dict[str, object] = {}
        list_names: list[str] = []
        lengths: set[int] = set()
        for name, raw in node.variables:
            value = raw
            if isinstance(raw, str):
                evaluated = self._eval_arg(self.ctx.current_frame, raw)
                if evaluated is not _MISSING:
                    value = evaluated
                elif _PARAM_REF.match(raw.strip()):
                    self._note_failure(node, f"Parallel 变量 '{name}' 引用的变量未定义")
                    return FAILURE
            parsed = self._as_foreach_list(value)
            values[name] = parsed if parsed is not None else value
            if parsed is not None:
                list_names.append(name)
                lengths.add(len(parsed))
        if len(lengths) > 1:
            self._note_failure(node, f"Parallel 列表变量长度不一致: {sorted(lengths)}")
            return FAILURE
        count = next(iter(lengths)) if lengths else 1
        if count == 0:
            return SUCCESS
        max_workers = max(1, min(int(node.max_concurrency), count))
        self._parallel_seq += 1
        group = f"Parallel#{self._parallel_seq}"
        parent = self.ctx.current_frame
        previous_failure = self.ctx.failure_reason
        seed = {name: self._copy_parallel_value(value) for name, value in parent.storage.items()}
        meta = self._meta_stack[-1] if self._meta_stack else {}
        meta["details"] = {
            "变量": {name: self._value_summary(value) for name, value in values.items()},
            "迭代次数": count,
            "最大并发": max_workers,
            "并行组": group,
        }
        label_prefix = f"{self.ctx.parallel_label}/" if self.ctx.parallel_label else ""

        def run_one(index: int) -> dict:
            label = f"{label_prefix}{group}[{index + 1}]"
            started = time.monotonic()
            reason = None
            changes: dict[str, tuple[object, str]] = {}
            try:
                worker_ctx, frame = self._make_parallel_context(
                    parent, values, list_names, index, label
                )
                traverser = Traverser(worker_ctx)
                traverser._depth = self._depth
                status = traverser.tick(node.body)
                reason = worker_ctx.failure_reason
                changes = self._parallel_changes(frame, seed, set(values))
            except Exception as exc:  # noqa: BLE001 - 单项异常按失败聚合
                logger.warning("并行迭代异常（%s）: %s", label, exc, exc_info=True)
                status = FAILURE
                reason = f"并行迭代异常: {exc}"
            return {
                "index": index,
                "status": status,
                "reason": reason,
                "elapsed": round(time.monotonic() - started, 3),
                "label": label,
                "changes": changes,
            }

        results: list[dict] = []
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=group) as pool:
            futures = [pool.submit(run_one, index) for index in range(count)]
            for future in as_completed(futures):
                results.append(future.result())
        results.sort(key=lambda item: item["index"])
        successes = [result for result in results if result["status"] == SUCCESS]
        failures = [result for result in results if result["status"] == FAILURE]
        conflicts, merge_error = self._merge_parallel_changes(
            parent, successes, set(values), node.on_conflict
        )
        meta["details"]["成功"] = len(successes)
        meta["details"]["失败"] = len(failures)
        meta["details"]["结果"] = [
            {
                "迭代": result["index"] + 1,
                "状态": result["status"],
                "并行": result["label"],
                "耗时": result["elapsed"],
                "失败原因": result["reason"],
            }
            for result in results
        ]
        if conflicts:
            meta["details"]["变量冲突"] = conflicts
        failed = bool(failures) and (
            node.on_failure == "abort" or not successes or merge_error is not None
        )
        if merge_error is not None:
            failed = True
            meta["details"]["变量回写错误"] = merge_error
        if not failed:
            return SUCCESS
        first_failure = failures[0]["reason"] if failures else None
        if first_failure is not None:
            self.ctx.failure_reason = first_failure
        elif merge_error is not None:
            self.ctx.failure_reason = merge_error
        else:
            self.ctx.failure_reason = previous_failure
            self._note_failure(node, "Parallel 全部迭代失败")
        return FAILURE

    @staticmethod
    def _as_foreach_list(value: object) -> list | None:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text or not text.startswith("["):
                return None
            try:
                parsed = json.loads(text)
            except (TypeError, ValueError):
                return None
            return parsed if isinstance(parsed, list) else None
        return None

    def _tick_finish(self, node: FinishNode) -> NodeStatus:
        """Finish：完成/终止（报告节点，纯程序），恒为 SUCCESS。"""
        return SUCCESS

    # ------------------------------------------------------------ 叶子触发

    @staticmethod
    def _coerce_function_arg(
        name: str, value: object, property_defs: dict
    ) -> object:
        """按参数声明转换/校验：array/object 构造，插件自定义类型做 isinstance 校验。"""
        prop = property_defs.get(name) or {}
        type_name = prop.get(AUTOBRANCH_TYPE_KEY) or prop.get("type")
        if type_name in ("array", "object"):
            return coerce(type_name, value)
        spec = TYPE_REGISTRY.get(type_name) if isinstance(type_name, str) else None
        if spec is not None and spec.custom:
            check_type(type_name, value)
        return value

    def _tick_function_call(self, node: FunctionCallNode) -> NodeStatus:
        """FunctionCall 节点：确定性调用插件函数（不经 LLM），回收返回值。"""
        meta = self._meta_stack[-1] if self._meta_stack else {}
        meta["function"] = node.function
        registry = self.ctx.registry
        if registry is None:
            return (
                self._note_failure(node, "FunctionCall 需要插件注册表（未注入 registry）")
                or FAILURE
            )
        spec = registry.function(node.function)
        if spec is None:
            return self._note_failure(node, f"函数不存在: {node.function}") or FAILURE
        if getattr(spec, "user_visible", True) is False:
            return (
                self._note_failure(
                    node, f"函数 {node.function} 仅供 LLM 调用，不能用于 FunctionCall"
                )
                or FAILURE
            )
        frame = self.ctx.current_frame
        required = list((spec.parameters or {}).get("required", []))
        property_defs = dict((spec.parameters or {}).get("properties", {}))
        properties = list(property_defs)
        param_names = properties or required
        if len(node.args) > len(param_names):
            return (
                self._note_failure(
                    node,
                    f"函数 {node.function} 位置实参数量 {len(node.args)} 超过参数总数 "
                    f"{len(param_names)}",
                )
                or FAILURE
            )
        args: dict[str, object] = {}
        for name, expr in zip(param_names, node.args, strict=False):
            val = self._eval_value(frame, expr)
            if val is _MISSING:
                return self._note_failure(node, f"实参 '{expr}' 求值失败（变量未定义）") or FAILURE
            try:
                args[name] = self._coerce_function_arg(name, val, property_defs)
            except SchemaError as exc:
                return (
                    self._note_failure(node, f"实参 {name} 类型转换失败: {exc}")
                    or FAILURE
                )
        for name, raw in node.kwargs or ():
            if name not in param_names or name in args:
                return self._note_failure(node, f"命名参数非法或重复: {name}") or FAILURE
            val = self._eval_value(frame, raw)
            if val is _MISSING:
                return (
                    self._note_failure(
                        node, f"命名参数 '{name}' 求值失败（变量未定义）"
                    )
                    or FAILURE
                )
            try:
                args[name] = self._coerce_function_arg(name, val, property_defs)
            except SchemaError as exc:
                return (
                    self._note_failure(node, f"命名参数 {name} 类型转换失败: {exc}")
                    or FAILURE
                )
        missing = [name for name in required if name not in args]
        if missing:
            return (
                self._note_failure(node, f"缺少必填参数: {', '.join(missing)}")
                or FAILURE
            )
        meta["arguments"] = dict(args)
        meta["kwargs"] = {
            name: args[name]
            for name, _raw in (node.kwargs or ())
            if name in args
        }
        try:
            result = registry.call(node.function, args, runtime=self.ctx.runtime)
        except Exception as exc:  # noqa: BLE001
            import traceback

            detail = traceback.format_exc()
            meta["failure_reason"] = f"函数 {node.function} 执行异常: {exc}\n{detail}"
            return self._note_failure(
                node, f"函数 {node.function} 执行异常: {exc}"
            ) or FAILURE
        if not result.ok:
            error = result.error or "函数执行失败"
            traceback_text = (result.detail or {}).get("traceback")
            meta["failure_reason"] = (
                f"{error}\n{traceback_text}" if traceback_text else error
            )
            return self._note_failure(node, f"函数 {node.function} 失败: {error}") or FAILURE
        outputs: dict[str, object] = {}
        for i, (recv, typ) in enumerate(node.returns):
            if i >= len(result.values):
                break
            value = result.values[i]
            outputs[recv] = value
            declared = (
                frame.declared.get(recv) or frame.outputs.get(recv) or frame.inputs.get(recv)
            )
            try:
                self.ctx.space.write(
                    frame, f"this/{recv}", value, declared or typ or infer_type(value)
                )
            except SchemaError as exc:
                meta["failure_reason"] = f"返回值写入变量 '{recv}' 失败: {exc}"
                return self._note_failure(node, f"返回值写入变量 '{recv}' 失败: {exc}") or FAILURE
        meta["returns"] = outputs
        return SUCCESS

    def _tick_define(self, node: DefineNode) -> NodeStatus:
        """Define 节点：确定性创建变量（值可 `Param.x` 读当前帧 / 字面量，coerce 后写帧）。"""
        frame = self.ctx.current_frame
        meta = self._meta_stack[-1] if self._meta_stack else {}
        defined: dict[str, object] = {}
        for name, type_name, expr in node.vars:
            value = self._eval_arg(frame, expr or "")
            if value is _MISSING:
                return (
                    self._note_failure(
                        node, f"Define 变量 '{name}' 的取值 '{expr}' 求值失败（变量未定义）"
                    )
                    or FAILURE
                )
            try:
                value = coerce(type_name, value)
            except SchemaError as exc:
                return (
                    self._note_failure(
                        node, f"Define 变量 '{name}' 类型转换失败（{type_name}）: {exc}"
                    )
                    or FAILURE
                )
            try:
                self.ctx.space.write(frame, f"this/{name}", value, type_name)
                defined[name] = value
            except SchemaError as exc:
                return self._note_failure(node, f"Define 变量 '{name}' 写入失败: {exc}") or FAILURE
        meta["details"] = {"变量": defined}
        return SUCCESS

    def _tick_predicate_condition(self, node: ConditionNode) -> NodeStatus:
        """执行确定性谓词条件；异常/非 bool 结果不等于 false。"""
        self._predicate_error = None
        started = time.monotonic()
        details: list[dict] = []
        value, error = self._eval_predicate(node.expression, details, "expression")
        if error is not None:
            self._predicate_error = error
            self._note_failure(node, error)
        status: NodeStatus = SUCCESS if error is None and value is True else FAILURE
        report = NodeReport(
            node_type="Condition",
            node_desc=_predicate_summary(node.expression),
            result="success" if status == SUCCESS else "failure",
            timestamp=_now_iso(),
            condition_result=value if error is None else None,
            duration=round(time.monotonic() - started, 3),
            failure_reason=error,
            details={
                "条件模式": "predicate",
                "表达式": _predicate_summary(node.expression),
                "求值": details,
                "最终结果": value if error is None else None,
            },
            parallel=self.ctx.parallel_label,
        )
        self.ctx.reporter.record_node(report)
        return status

    def _eval_predicate(
        self, expr: PredicateExpr | None, details: list[dict], path: str
    ) -> tuple[bool | None, str | None]:
        if expr is None:
            return None, "谓词条件缺少 expression"
        if isinstance(expr, PredicateCall):
            return self._eval_predicate_call(expr, details, path)
        if expr.op == "not":
            if len(expr.children) != 1:
                return None, "NOT 必须恰好一个子条件"
            value, error = self._eval_predicate(expr.children[0], details, f"{path}.not")
            if error is not None:
                return None, error
            return (not bool(value)), None
        if expr.op not in ("all", "any"):
            return None, f"未知谓词逻辑操作: {expr.op}"
        short_circuit = False
        result = expr.op == "all"
        for index, child in enumerate(expr.children):
            value, error = self._eval_predicate(child, details, f"{path}.{expr.op}[{index}]")
            if error is not None:
                return None, error
            if expr.op == "all" and value is False:
                result = False
                short_circuit = True
                break
            if expr.op == "any" and value is True:
                result = True
                short_circuit = True
                break
        details.append(
            {"路径": path, "逻辑": expr.op.upper(), "结果": result, "短路": short_circuit}
        )
        return result, None

    def _eval_predicate_call(
        self, call: PredicateCall, details: list[dict], path: str
    ) -> tuple[bool | None, str | None]:
        registry = self.ctx.registry
        if registry is None:
            return None, "谓词条件需要插件注册表（未注入 registry）"
        spec = registry.function(call.function)
        if spec is None:
            return None, f"谓词函数不存在: {call.function}"
        frame = self.ctx.current_frame
        property_defs = dict((spec.parameters or {}).get("properties", {}))
        param_names = list(property_defs) or list((spec.parameters or {}).get("required", []))
        if len(call.args) > len(param_names):
            return None, f"谓词函数 {call.function} 位置参数过多"
        args: dict[str, object] = {}
        for name, expr in zip(param_names, call.args, strict=False):
            val = self._eval_arg(frame, expr)
            if val is _MISSING:
                return None, f"谓词参数 '{expr}' 求值失败（变量未定义）"
            try:
                args[name] = self._coerce_function_arg(name, val, property_defs)
            except SchemaError as exc:
                return None, f"谓词参数 {name} 类型转换失败: {exc}"
        for name, raw in call.kwargs:
            if name not in param_names or name in args:
                return None, f"谓词命名参数非法或重复: {name}"
            val = self._eval_value(frame, raw)
            if val is _MISSING:
                return None, f"谓词命名参数 '{name}' 求值失败（变量未定义）"
            try:
                args[name] = self._coerce_function_arg(name, val, property_defs)
            except SchemaError as exc:
                return None, f"谓词命名参数 {name} 类型转换失败: {exc}"
        try:
            result = registry.call(call.function, args, runtime=self.ctx.runtime)
        except Exception as exc:  # noqa: BLE001
            return None, f"谓词函数 {call.function} 执行异常: {exc}"
        if not result.ok:
            return None, f"谓词函数 {call.function} 失败: {result.error or '未知错误'}"
        if len(result.values) != 1 or not isinstance(result.values[0], bool):
            return None, f"谓词函数 {call.function} 必须返回单个 bool"
        value = bool(result.values[0])
        details.append(
            {
                "路径": path,
                "函数": call.function,
                "参数": args,
                "结果": value,
            }
        )
        return value, None

    def _tick_leaf(self, node: ActionNode | ConditionNode) -> NodeStatus:
        """Action/Condition 叶子：触发 M6 执行、接收 ``LeafResult``，返回前截图。"""
        node_type = "Action" if isinstance(node, ActionNode) else "Condition"
        timeout = self._effective_timeout(node)
        result, elapsed = self._execute_leaf(node, timeout)
        timed_out = timeout is not None and elapsed > timeout

        status: NodeStatus = FAILURE
        if not timed_out and result.status == "success":
            status = SUCCESS
        if status == FAILURE:
            self._note_failure(node, _leaf_failure_text(node_type, result, timed_out, timeout))

        screenshot_path = ""
        page_url = None
        if result.used_browser:
            # 仅浏览器叶子在**执行后**拍当前页面状态（操作/判断结果）；
            # 纯计算叶子不截图，也不在报告中展示。
            page_ref = self.ctx.browser.current_page()
            if page_ref is not None:
                try:
                    handle = self.ctx.browser.page(page_ref)
                    if getattr(handle, "ok", False):
                        page_url = handle.detail["page"].url
                except Exception:
                    page_url = None
                shot = self.ctx.reporter.capture_screenshot(page_ref, node.description)
                if shot:
                    screenshot_path = self._report_rel_path(shot)
            if not screenshot_path and result.screenshots:
                # 兜底：无当前页时用浏览器插件 semantic_graph 产出的截图
                screenshot_path = self._report_rel_path(result.screenshots[0])
        failure_reason = (
            _leaf_failure_text(node_type, result, timed_out, timeout)
            if status == FAILURE
            else None
        )
        report = NodeReport(
            node_type=node_type,
            node_desc=self._describe_with_values(node, node.description),
            result="success" if status == SUCCESS else "failure",
            timestamp=_now_iso(),
            action_call=_primary_action_call(node, result),
            condition_result=result.bool_value if isinstance(node, ConditionNode) else None,
            page_url=page_url,
            screenshot_path=screenshot_path or None,
            llm_trace=result.trace,
            duration=round(elapsed, 3),
            failure_reason=failure_reason,
            parallel=self.ctx.parallel_label,
        )
        self.ctx.reporter.record_node(report)
        return status

    def _execute_leaf(self, node: Node, timeout: float | None) -> tuple[LeafResult, float]:
        """触发叶子执行；普通异常包装为程序侧失败，致命错误上抛。"""
        try:
            start = time.monotonic()
            result = self.ctx.leaf_executor(node, timeout)
            return result, time.monotonic() - start
        except FatalBrowserError:
            raise
        except Exception as exc:
            logger.warning("叶子执行抛出未预期异常（%s）: %s", node_desc(node), exc)
            trace = LeafTrace(
                llm_input={
                    "node_type": node_type_name(node),
                    "node_desc": node_desc(node),
                    "error": str(exc),
                }
            )
            return LeafResult(status="failure", error_source="program", trace=trace), 0.0

    def _effective_timeout(self, node: Node | None = None) -> float | None:
        """节点生效超时：节点级 timeout → 帧配置（自身 → 祖先 → 全局默认）。"""
        if isinstance(node, ActionNode) and node.timeout is not None:
            return float(node.timeout)
        frame = self.ctx.current_frame
        if frame is None:
            return None
        value = self.ctx.space.resolve_config(frame, "timeout")
        if value is None:
            return None
        return float(value)

    # ------------------------------------------------------------ ref 动态调用

    def _tick_ref(self, node: RefNode) -> NodeStatus:
        """ref 运行时动态调用（一文档一树）：加载被引文档 → 从其 Root 执行。

        执行顺序（§3 执行模型）：
        1. 经 resolver 按文档名加载被引文档，解析其主树与文档级声明。
        2. 求值每个实参（``this/<名>``/裸变量名读父帧；非变量按字面量），
           按序对应被引文档 ``inputs``；coerce 到声明类型。
        3. ``enter_frame`` 建子帧，cast 后形参写入子帧（``this/形参名``）。
        4. 递归 ``tick`` 被引文档主树（从 Root 执行；其内部 ref 由各自 _tick_ref 管理）。
        5. 被引树 SUCCESS → 按 ``returns``（按序对应 ``outputs``）读子帧输出
           写父帧局部变量；FAILURE → 不写 returns，失败向上传播。
        6. ``exit_frame`` 退出子帧（数据保留至 run 结束）。
        """
        target = (node.ref_target or "").strip()
        if not target or "/" in target:
            msg = f"ref 目标非法（应为文档名单段）: {target!r}"
            return self._note_failure(node, msg) or FAILURE
        loaded = self._load_doc_tree(target)
        if loaded is None:
            return self._note_failure(node, f"引用文档不存在或无法解析: {target!r}") or FAILURE
        child_tree, decl = loaded
        space = self.ctx.space
        parent = self.ctx.current_frame
        meta = self._meta_stack[-1] if self._meta_stack else {}
        meta["details"] = {"target": target}
        input_types = dict(decl.inputs) if decl else {}
        input_names = list(input_types)
        # 2) 求值 args（按序对应 inputs）：变量读父帧；非变量按字面量
        args_values: dict[str, object] = {}
        if len(node.args) != len(input_names):
            return (
                self._note_failure(
                    node,
                    f"实参数量 {len(node.args)} 与被引文档 '{target}' "
                    f"入参数量 {len(input_names)} 不符",
                )
                or FAILURE
            )
        for i, expr in enumerate(node.args):
            name = input_names[i]
            val = self._eval_value(parent, expr)
            if val is _MISSING:
                return (
                    self._note_failure(node, f"实参 '{expr!r}' 求值失败（变量未定义）")
                    or FAILURE
                )
            args_values[name] = val
        meta["arguments"] = dict(args_values)
        # coerce 到输入类型
        typed: dict[str, object] = {}
        for name, val in args_values.items():
            t = input_types.get(name, "")
            typed[name] = coerce(t, val) if t else val
        # 3) 建子帧（注入 inputs/config）
        frame = None
        try:
            frame = space.enter_frame(target, decl, mount=space.root)
            for name, val in typed.items():
                space.write(
                    frame, f"this/{name}", val, input_types.get(name, "") or infer_type(val)
                )
            # 4) 递归执行被引文档主树（从 Root 执行）
            status = self.tick(child_tree)
            # 5) SUCCESS → returns 回收写父帧（按序对应 outputs）
            if status == SUCCESS:
                out_names = list(decl.outputs) if decl else []
                outputs: dict[str, object] = {}
                for i, (recv_name, _typ) in enumerate(node.returns):
                    if i >= len(out_names):
                        continue
                    value = space.read(frame, f"this/{out_names[i]}")  # 子帧读输出
                    if value is not None:
                        outputs[recv_name] = value
                        declared = (
                            parent.declared.get(recv_name)
                            or parent.outputs.get(recv_name)
                            or parent.inputs.get(recv_name)
                        )
                        space.write(
                            parent,
                            f"this/{recv_name}",
                            value,
                            declared or _typ or infer_type(value),
                        )
                meta["returns"] = outputs
        finally:
            if frame is not None:
                # 6) 退出子帧（数据保留至 run 结束）
                space.exit_frame()
        return status

    def _load_doc_tree(self, doc_id: str) -> tuple[Node, object] | None:
        """经 resolver 加载被引文档（并发时按 resolver_lock 串行）。"""
        resolver = self.ctx.resolver
        if resolver is None:
            return None
        lock = self.ctx.resolver_lock
        if lock is None:
            return self._load_doc_tree_unlocked(doc_id, resolver)
        with lock:
            return self._load_doc_tree_unlocked(doc_id, resolver)

    def _load_doc_tree_unlocked(
        self, doc_id: str, resolver
    ) -> tuple[Node, object] | None:
        try:
            src = resolver.resolve(doc_id)
        except Exception:
            return None
        try:
            from autobranch.parser.onedoc import parse_document as parse_onedoc

            ores = parse_onedoc(src, resolver)
        except Exception:
            return None
        if not ores.checks_ok() or ores.main_tree is None:
            return None
        from autobranch.parser.expand import ExpandContext, expand_document

        ectx = ExpandContext(max_depth=64)
        expansion = expand_document(ores.main_tree, ectx, decl_inputs=ores.decl_inputs)
        decl = FrameDecl(
            name=doc_id,
            inputs=dict(ores.decl_inputs),
            outputs=dict(ores.decl_outputs),
            config=dict(ores.config),
        )
        return expansion.tree, decl

    def _eval_value(self, frame, value):
        """求值 kwargs 值：字符串走字面量/Param 规则；dict/list 递归求值。"""
        if isinstance(value, str):
            return self._eval_arg(frame, value)
        if isinstance(value, list):
            items = [self._eval_value(frame, item) for item in value]
            return _MISSING if any(item is _MISSING for item in items) else items
        if isinstance(value, dict):
            result: dict[str, object] = {}
            for key, item in value.items():
                evaluated = self._eval_value(frame, item)
                if evaluated is _MISSING:
                    return _MISSING
                result[str(key)] = evaluated
            return result
        return value

    def _eval_arg(self, frame, expr: str):
        """求值实参表达式：``Param.<名>`` → 读当前帧变量（未定义返回 ``_MISSING`` 哨兵）；
        其余一律按字面量解析（``_parse_literal``）。消除旧版"裸名命中变量否则字面量"的二义性。
        """
        text = expr or ""
        m = _PARAM_REF.fullmatch(text.strip())
        if m:
            return self._read_param(frame, m.group(1), m.group(2))
        if not _PARAM_REF.search(text):
            return _parse_literal(text)
        missing = False

        def _replace(match: re.Match) -> str:
            nonlocal missing
            value = self._read_param(frame, match.group(1), match.group(2))
            if value is _MISSING:
                missing = True
                return match.group(0)
            return self._value_summary(value)

        replaced = _PARAM_REF.sub(_replace, text)
        return _MISSING if missing else replaced

    # ------------------------------------------------------------ 报告与状态

    def _start_node(self, node: Node) -> None:
        self.ctx.reporter.start_node(
            NodeInfo(
                node_type=node_type_name(node),
                node_desc=node_desc(node),
                parallel=self.ctx.parallel_label,
            )
        )

    def _record_node(
        self, node: Node, status: NodeStatus, meta: dict, started: float
    ) -> None:
        failure_reason = meta.get("failure_reason")
        if status == FAILURE and not failure_reason:
            failure_reason = self.ctx.failure_reason
        self.ctx.reporter.record_node(
            NodeReport(
                node_type=node_type_name(node),
                node_desc=self._describe_with_values(node, node_desc(node)),
                result="success" if status == SUCCESS else "failure",
                timestamp=_now_iso(),
                duration=round(time.monotonic() - started, 3),
                failure_reason=failure_reason,
                function=meta.get("function"),
                arguments=meta.get("arguments"),
                kwargs=meta.get("kwargs"),
                returns=meta.get("returns"),
                details=meta.get("details"),
                parallel=self.ctx.parallel_label,
            )
        )

    def _describe_with_values(self, node: Node, text: str) -> str:
        if not isinstance(node, (ActionNode, ConditionNode)) or not text:
            return text
        frame = self.ctx.current_frame
        if frame is None or self.ctx.space is None:
            return text

        def _replace(match: re.Match) -> str:
            value = self._read_param(frame, match.group(1), match.group(2))
            if value is _MISSING:
                return match.group(0)
            return f"{match.group(0)} ({self._value_summary(value)})"

        return _PARAM_REF.sub(_replace, text)

    def _read_param(self, frame, var: str, suffix: str) -> object:
        if self.ctx.space is None or not self.ctx.space.has_variable(frame, var):
            return _MISSING
        value = self.ctx.space.read(frame, var)
        if not suffix:
            return value
        try:
            return read_path_value(value, suffix.lstrip("."))
        except SchemaError:
            return _MISSING

    @staticmethod
    def _value_summary(value: object, limit: int = 200) -> str:
        text = str(value)
        return text if len(text) <= limit else text[:limit] + "…"

    def _note_failure(self, node: Node, text: str) -> None:
        """记录首个失败节点描述（根统一终止时的失败原因，指向失败叶子）。"""
        if self.ctx.failure_reason is not None:
            return
        loc = node.loc.path if node.loc is not None else "?"
        self.ctx.failure_reason = (
            f"{node_type_name(node)}『{node_desc(node)}』失败: {text}（位于 {loc}）"
        )

    def _report_rel_path(self, path: str) -> str:
        """截图绝对路径 → 相对报告根（供前端 ``/api/reports/{path}`` 提供）。"""
        if not path:
            return ""
        try:
            base = os.path.abspath(self.ctx.config.report_dir)
            rel = os.path.relpath(os.path.abspath(path), base)
            return rel.replace(os.sep, "/")
        except Exception:
            return path

    def _check_depth(self) -> None:
        if self._depth >= _MAX_RECURSION_DEPTH:
            raise OrchestratorError(f"遍历嵌套过深（超过 {_MAX_RECURSION_DEPTH} 层）")


#: 实参求值失败哨兵（与有效值区分；None 是合法存储值）。
_MISSING = object()


#: ``Param.<名>`` 变量引用（实参求值用；ASCII 词边界防 ``NewParam.`` 误判）
_PARAM_REF = re.compile(
    r"(?<![A-Za-z0-9_])Param\.([A-Za-z_][A-Za-z0-9_]*)((?:\.[A-Za-z0-9_]+)*)"
)


def _parse_literal(expr: str):
    """把字面量表达式转成基础值（str/int/float/bool）。

    ``strip()`` 仅用于 bool/数值识别；字符串回退保留原始前后空白，避免破坏
    命令拼接、分隔符等对空格敏感的字面量。
    """
    s = (expr or "").strip()
    lowered = s.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return expr or ""


def _leaf_failure_text(
    node_type: str, result: LeafResult, timed_out: bool, timeout: float | None
) -> str:
    """叶子失败原因文本（供 ``failure_reason`` 展示）。"""
    if timed_out:
        return f"执行超时（>{timeout} 秒）"
    if result.error_source == "program":
        term = result.trace.terminator or "程序侧失败"
        return f"程序侧失败（{term}）"
    term = result.trace.terminator or "LLM 侧失败"
    return f"LLM 侧失败（{term}）"


def _primary_action_call(node: Node, result: LeafResult) -> ActionCall | None:
    """Action 专有：从执行追踪的首个工具调用派生 ``ActionCall``（无则 None）。"""
    if not isinstance(node, ActionNode):
        return None
    calls = result.trace.calls
    if not calls:
        return None
    first = calls[0]
    return ActionCall(
        function=first.name,
        success=bool(first.success),
        arguments=first.arguments,
        error=None,
    )


__all__ = [
    "Traverser",
    "node_type_name",
    "node_desc",
    "count_nodes",
    "NodeStatus",
]
