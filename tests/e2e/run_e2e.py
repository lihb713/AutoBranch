"""WebOps 端到端真实验证（一次性验证工具，不纳入常规 pytest）。

真实接线 M0~M8 跑通完整链路：
  M2 解析行为树 → M7 Engine.run → 冷启动 M1 浏览器 → 遍历 →
  M6 叶子 agent（M0 LLM 会话 + M5 引擎函数）→ M4 语义图 → M8 报告。

配置来源（webops/config.py 统一加载）：
  - 项目根 ``webops.config.json``（或 ``--config <path>`` / ``WEB_OPS_CONFIG``）
  - api_key 可留空，由环境变量 ``WEB_OPS_LLM_API_KEY`` 注入（安全）

报告输出：固定写入项目 ``reports/`` 目录（``run.report_dir`` 配置项，
默认 ``reports``），每个 run 一个子目录 ``reports/<run_id>/``。

用法：
  $env:WEB_OPS_LLM_API_KEY="sk-..."          # 密钥注入（必填）
  conda run -n webops python tests/e2e/run_e2e.py [--config webops.config.json]
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGES_DIR = HERE / "pages"
FLOWS_DIR = HERE / "flows"
ROOT = HERE.parents[1]

sys.path.insert(0, str(ROOT))

from webops.config import WebOpsConfig  # noqa: E402


def _start_server() -> tuple[ThreadingHTTPServer, threading.Thread]:
    handler = SimpleHTTPRequestHandler
    os.chdir(PAGES_DIR)
    server = ThreadingHTTPServer(("127.0.0.1", 8123), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WebOps 端到端真实验证")
    parser.add_argument("--config", default=None, help="配置文件路径（默认 webops.config.json）")
    return parser.parse_args()


def main() -> int:
    from webops.browser import BrowserDriver
    from webops.engine import EngineFunctions
    from webops.orchestrator import Engine
    from webops.parser.models import DocumentSource
    from webops.parser.parser import BehaviorTreeParser
    from webops.parser.refs import MappingResolver
    from webops.schema import SchemaSpace

    args = _parse_args()
    cfg = WebOpsConfig.load(args.config)

    if not cfg.llm.api_key:
        print("[错误] 未配置 api_key：请在 webops.config.json 填入，或设置环境变量"
              " WEB_OPS_LLM_API_KEY")
        return 2
    llm_config = cfg.to_llm_config()

    server, thread = _start_server()
    print("[1/6] 本地测试页面已启动: http://127.0.0.1:8123/index.html")
    print(f"      LLM 配置: model={cfg.llm.model} base_url={cfg.llm.base_url}")

    try:
        # ---- 解析行为树（M2）----
        flow_file = FLOWS_DIR / "订单审批.yaml"
        source = flow_file.read_text(encoding="utf-8")
        resolver = MappingResolver({})
        result = BehaviorTreeParser().parse(
            DocumentSource(id="订单审批", data=source),
            resolver,
        )
        if not result.checks.ok:
            print("[错误] 行为树清晰度校验失败:")
            for issue in result.checks.issues:
                print(f"  - {issue.code}: {issue.message}")
            return 3
        print(f"[2/6] 行为树解析通过，节点树: {result.tree.name}")

        # ---- 装配（M1/M3/M4/M5）----
        browser = BrowserDriver()
        schema_space = SchemaSpace()

        def current_frame():
            return schema_space._current

        def graph_generator(
            page_ref, scope="full", lod=2, probe=None, filler=None, budget_limit=None
        ):
            # 语义图生成：用 MockFiller 提供确定性语义（秒级），agent 决策用真实 LLM。
            # 真实 LLM 语义图填充质量已单独验证（见 tests/e2e/README）。
            from webops.browser.models import LODSpec
            from webops.semantic_graph.llm_fill import MockFiller
            from webops.semantic_graph.pipeline import generate_semantic_graph

            snapshot = probe.crawl(page_ref, LODSpec.from_level(3))
            mock = MockFiller(
                purposes={
                    "username": "用户名输入框",
                    "password": "密码输入框",
                    "login-btn": "登录按钮",
                    "order-id-1": "订单号",
                    "customer-1": "客户名",
                    "amount-1": "金额",
                    "status-1": "状态",
                    "approve-btn-1": "批准按钮",
                    "order-id-2": "订单号",
                    "customer-2": "客户名",
                    "amount-2": "金额",
                    "status-2": "状态",
                    "approve-btn-2": "批准按钮",
                }
            )
            return generate_semantic_graph(
                snapshot, scope=scope, lod=lod, filler=mock, budget_limit=budget_limit
            )

        engine_functions = EngineFunctions(
            browser=browser,
            filler=None,  # 被自定义 graph_generator 覆盖
            schema_space=schema_space,
            current_frame=current_frame,
            graph_generator=graph_generator,
        )

        # ---- 执行（M7 + M6 + M0）----
        # 报告固定写入项目根 reports/（配置项 run.report_dir，相对路径按项目根解析）
        report_dir = str((ROOT / cfg.run.report_dir).resolve())
        Path(report_dir).mkdir(parents=True, exist_ok=True)
        config = cfg.to_run_config(
            timeout=600.0,
            report_dir=report_dir,  # 绝对路径，避免受工作目录影响
            llm_config=llm_config,
            engine=engine_functions,
        )
        engine = Engine(browser=browser, space_factory=lambda: schema_space)
        print(f"[3/6] 开始执行行为树（真实浏览器 + 真实 LLM: {cfg.llm.model}）...")
        started = time.time()
        run_result = engine.run(
            result.tree,
            config,
            resolver=resolver,
            blocks_tree=result.blocks_tree,
            decl_inputs=result.decl_inputs,
            decl_outputs=result.decl_outputs,
            config_overrides=result.config,
        )
        elapsed = time.time() - started
        print(f"[4/6] 执行完成，耗时 {elapsed:.1f}s，状态: {run_result.status}")
        if run_result.failure_reason:
            print(f"  失败原因: {run_result.failure_reason}")

        # ---- 报告输出（固定 reports/ 目录）----
        print(f"[5/6] 报告目录: {report_dir}")
        if run_result.exec_report:
            print(f"  执行报告: {run_result.exec_report.path}")
        if run_result.trace_report:
            print(f"  回溯报告: {run_result.trace_report.path}")

        # ---- 摘要 ----
        state = engine.get_exec_state()
        print(f"[6/6] 执行状态: finished={state.finished}, completed={len(state.completed)} 节点")
        return 0 if run_result.status == "success" else 1
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    sys.exit(main())
