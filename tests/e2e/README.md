# AutoBranch 端到端真实验证

本目录是一次性端到端验证工具：真实接线 M0~M8 跑通完整链路
（行为树解析 → 引擎冷启动 → 遍历 → 叶子 agent 执行 → 报告），验证系统
「流程流转确定、LLM 在单节点内有界执行」的核心设计在真实页面 + 真实 LLM
下可工作。**不纳入常规 pytest**（依赖真实网络与 LLM 密钥）。

## 组成

| 文件 | 说明 |
|---|---|
| `pages/index.html` | 本地测试页面：登录表单 + 订单列表（批准按钮），前端 JS 模拟登录/批准 |
| `flows/订单审批.yaml` | 真实业务行为树：打开页面 → 登录 → 提取订单号 → 点击批准 → 验证状态 |
| `run_e2e.py` | 端到端执行脚本（真实浏览器 + 真实 LLM agent 决策，统一配置加载） |
| `autobranch.config.json`（项目根） | 统一配置：llm / browser / run（api_key 留空，环境变量注入） |

## 运行

```bash
# 1) 配置：项目根 autobranch.config.json（api_key 留空，由环境变量注入）
#    或拷贝并修改：--config <path> 指定
# 2) 注入真实 LLM 密钥（opencode Go 订阅端点，或任意 OpenAI 兼容端点）
$env:AUTOBRANCH_LLM_API_KEY="sk-..."
#    （可选覆盖端点/模型：autobranch.config.json 的 llm.base_url / llm.model）

conda run -n autobranch python tests/e2e/run_e2e.py [--config autobranch.config.json]
```

脚本输出执行状态、报告路径与执行进度；`engine.get_exec_state()` 返回
节点完成情况。

## 报告位置

报告固定写入项目根 **`reports/`** 目录（`autobranch.config.json` 的
`run.report_dir`，默认 `reports`，相对项目根解析）。每次运行生成一个
子目录 `<reports>/<run_id>/`：

```
reports/<run_id>/
├── 001_<节点描述>.png ... 012_<节点描述>.png   # 每叶子截图
├── exec_report.md                                # 执行情况报告（每节点结果+截图路径）
└── trace_report.md                               # 回溯报告（LLM 推理全过程）
```

配置项 `run.report_dir` 可改到任意目录（如 `data/reports`）。

## 验证结论（2026-08-29 实测）

| 环节 | 结果 |
|---|---|
| 行为树解析（M2） | 6 组 Step 复合节点全部正确展开 |
| 引擎冷启动 + 遍历（M7） | 19 节点全部 SUCCESS，报告完整 |
| 叶子 agent 执行（M6+M0） | LLM 正确决策：open → type → click → extract → 验证 |
| 引擎函数（M5） | open/type/click/extract/semantic_graph 全部真实生效 |
| 语义图（M4） | 真实 LLM 填充质量高：purpose/related-to 关联合理（0.9+ 分） |
| 报告（M8） | 执行报告 + 回溯报告（含 LLM 推理过程）生成正确 |

完整业务闭环：登录成功 → 提取 `ORD-001` 订单号写入变量 → 点击第一行批准
按钮 → 验证该行状态变为「已批准」。全部由真实浏览器 + 真实 LLM 完成。

## 实测发现与已确认的集成要点

1. **M5 与 M7 必须共享同一个 `SchemaSpace`**：M7 `Engine.run` 默认每次
   新建 SchemaSpace（`space_factory`），而 M5 `EngineFunctions` 持有的
   schema_space 是外部注入的。若两者不同实例，M5 的 `open()` 写入页面
   引用时「当前帧不可用」（`frame_provider` 查到的是外部空 space）。
   **接线要求**：`Engine(browser=..., space_factory=lambda: schema_space)`，
   与 `EngineFunctions(schema_space=schema_space, current_frame=lambda: schema_space._current)`
   必须指向同一实例。

2. **真实语义图填充成本高**：每次 `semantic_graph` 含 2 次真实 LLM 请求
   （purpose + related-to 打分），实测单次 44~100s（受端点负载影响），
   偶尔超时。agent 循环中 LLM 若多次调用 semantic_graph，单个叶子可达
   分钟级。**建议**：业务部署时 LOD 用低档、提示词引导 LLM 一次取图到位。

3. **叶子语义图预取**：M6 每个叶子执行前预取一次初始语义图。页面未打开
   时预取失败（无当前页面变量）不终止，LLM 自行 open 后重取——实测正确。

4. **MockFiller 用于可重复验证**：为让端到端链路可重复（不依赖真实 LLM
   填充的慢/不稳定），`run_e2e.py` 用 `MockFiller` 提供确定性语义（按
   DOM id 键控 purpose），agent 决策仍用真实 LLM。真实 LLM 语义图质量
   已单独验证（见上表）。

## 回归

端到端验证不修改任何库代码。常规测试套件完整：
`conda run -n autobranch python -m pytest` → 646 passed（含真实浏览器集成）。