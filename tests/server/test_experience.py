"""经验回灌服务端测试（Change C 任务 1.1/1.3/1.4/3.1/3.2）。

覆盖：experiences 模型与级联；蒸馏（去 ref）；渲染；整树成功采集 / 失败不采集；
老化（保留 N 条）；三钥匙查询闭包；配置默认值与关闭路径。
"""

from __future__ import annotations

from autobranch.config import AutoBranchConfig
from autobranch.orchestrator.models import RunResult
from autobranch.reporting.models import (
    ExecState,
    LeafTrace,
    NodeReport,
    ToolCallRecord,
)
from autobranch.server.models import Experience, Run, Tree
from autobranch.server.services.engine import MockEngineService
from autobranch.server.services.runs import (
    RunService,
    distill_tool_calls,
    normalize_inputs,
    render_reference,
)

# ------------------------------------------------------------- 蒸馏与渲染（1.4）

_TRACE = LeafTrace(
    llm_input={"description": "登录用户: admin"},
    decision="结果: 成功",
    calls=[
        ToolCallRecord(
            name="semantic_graph",
            arguments={"scope": {"x": 0, "y": 0, "w": 10, "h": 10}},
            result="图",
            success=True,
        ),
        ToolCallRecord(
            name="click", arguments={"ref": 1, "target": "登录按钮"}, result="成功", success=True
        ),
        ToolCallRecord(
            name="click", arguments={"ref": 2, "target": "错误元素"}, result="失败", success=False
        ),
    ],
)


def test_distill_tool_calls_keeps_success_and_de_refs():
    calls = distill_tool_calls(_TRACE)
    assert [c["function"] for c in calls] == ["semantic_graph", "click"]
    # 失败尝试剔除
    assert len(calls) == 2
    # 去 ref 化：ref 编号与 scope 坐标不进入经验，target 保留
    assert "ref" not in calls[1]["arguments"]
    assert "scope" not in calls[0]["arguments"]
    assert calls[1]["arguments"]["target"] == "登录按钮"


def test_render_reference_contains_authority_declaration():
    text = render_reference(
        [{"function": "click", "arguments": {"target": "登录按钮"}, "result": "成功"}],
        "结果: 成功",
    )
    assert "仅供参考，以当前语义图为准" in text
    assert "与当前页面状态不符时忽略经验" in text
    assert "click" in text
    assert "最终决策: 结果: 成功" in text


def test_normalize_inputs_stable():
    assert normalize_inputs({"b": 2, "a": 1}) == normalize_inputs({"a": 1, "b": 2})
    assert normalize_inputs(None) == normalize_inputs({})


# ------------------------------------------------------------- 采集与老化（1.3/3.1）

def _run_service(tmp_path, config=None) -> tuple[RunService, MockEngineService]:
    engine = MockEngineService()
    service = RunService(
        engine, tmp_path / "reports", config or AutoBranchConfig(), registry=None
    )
    return service, engine


def _completed_state(*reports: NodeReport) -> ExecState:
    return ExecState(run_id="1", completed=list(reports), finished=True)


def test_collect_on_success_finalize(tmp_path, session):
    service, engine = _run_service(tmp_path)
    tree = Tree(name="exp1", content="tree: exp1\nnodes: {}")
    session.add(tree)
    session.commit()
    run = Run(
        tree_id=tree.id,
        status="running",
        content_snapshot="tree: exp1",
        tree_name_snapshot="exp1",
        tree_content_hash="hash1",
        inputs={"user": "admin"},
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    engine.set_final_state(
        run.id,
        _completed_state(
            NodeReport(
                node_type="Action",
                node_desc="登录用户: admin",
                result="success",
                timestamp="t",
                llm_trace=_TRACE,
            ),
            NodeReport(
                node_type="Condition", node_desc="出现工作台", result="success", timestamp="t"
            ),
        ),
    )
    service._finalize(session, run.id, RunResult(status="success"))
    rows = session.query(Experience).all()
    assert len(rows) == 1  # 仅带 llm_trace 的 Action 被采集
    assert rows[0].node_desc == "登录用户: admin"
    assert rows[0].inputs_norm == normalize_inputs({"user": "admin"})
    assert rows[0].tool_calls[0]["function"] == "semantic_graph"


def test_no_collect_on_failure(tmp_path, session):
    service, engine = _run_service(tmp_path)
    run = Run(status="running", content_snapshot="c", tree_name_snapshot="t", tree_content_hash="h")
    session.add(run)
    session.commit()
    session.refresh(run)
    service._finalize(session, run.id, RunResult(status="failure", failure_reason="x"))
    assert session.query(Experience).count() == 0


def test_aging_keeps_latest_n(tmp_path, session):
    config = AutoBranchConfig(experience_retention=2)
    service, _ = _run_service(tmp_path, config)
    tree = Tree(name="exp2", content="c")
    session.add(tree)
    session.commit()
    run = Run(
        tree_id=tree.id,
        status="success",
        content_snapshot="c",
        tree_name_snapshot="t",
        tree_content_hash="h",
        inputs={"user": "admin"},
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    inputs_norm = normalize_inputs(run.inputs)
    for i in range(5):
        session.add(
            Experience(
                run_id=run.id,
                tree_content_hash="h",
                inputs_norm=inputs_norm,
                node_desc=f"节点{i}",
                node_type="Action",
                tool_calls=[],
                decision="结果: 成功",
            )
        )
    session.commit()
    service._prune_experiences(session)
    assert session.query(Experience).count() == 5  # 不同 node_desc 分属不同组，不删
    # 同组 4 条 → 保留最新 2 条
    for _ in range(4):
        session.add(
            Experience(
                run_id=run.id,
                tree_content_hash="h",
                inputs_norm=inputs_norm,
                node_desc="同一节点",
                node_type="Action",
                tool_calls=[],
                decision="结果: 成功",
            )
        )
    session.commit()
    service._prune_experiences(session)
    group = session.query(Experience).filter(Experience.node_desc == "同一节点").all()
    assert len(group) == 2


# ------------------------------------------------------------- 查询闭包（2.3）

def test_lookup_matches_three_keys(tmp_path, session):
    service, _ = _run_service(tmp_path)
    tree = Tree(name="exp3", content="c")
    session.add(tree)
    session.commit()
    run = Run(
        tree_id=tree.id,
        status="success",
        content_snapshot="c",
        tree_name_snapshot="t",
        tree_content_hash="hash-x",
        inputs={"user": "admin"},
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    session.add(
        Experience(
            run_id=run.id,
            tree_content_hash="hash-x",
            inputs_norm=normalize_inputs({"user": "admin"}),
            node_desc="登录用户: admin",
            node_type="Action",
            tool_calls=[
                {"function": "click", "arguments": {"target": "登录按钮"}, "result": "成功"}
            ],
            decision="结果: 成功",
        )
    )
    session.commit()

    lookup = service._make_experience_lookup(run)
    assert lookup is not None
    assert "仅供参考" in (lookup("登录用户: admin") or "")
    assert lookup("登录用户: bob") is None  # 节点身份不符 → 不命中
    assert lookup("其他节点") is None


def test_lookup_disabled_returns_none(tmp_path, session):
    service, _ = _run_service(tmp_path, AutoBranchConfig(experience_feedback=False))
    run = Run(status="running", content_snapshot="c", tree_name_snapshot="t", tree_content_hash="h")
    session.add(run)
    session.commit()
    session.refresh(run)
    assert service._make_experience_lookup(run) is None


# ------------------------------------------------------------- 配置（3.2）

def test_config_defaults_and_overrides(tmp_path):
    cfg = AutoBranchConfig()
    assert cfg.experience_feedback is True
    assert cfg.experience_retention == 5
    over = AutoBranchConfig.from_dict({"experience_feedback": False, "experience_retention": 3})
    assert over.experience_feedback is False
    assert over.experience_retention == 3
