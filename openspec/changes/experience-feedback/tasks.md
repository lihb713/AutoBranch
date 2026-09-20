# experience-feedback 任务

## 1. 经验数据模型与采集

- [ ] 1.1 新增 `experiences` 模型（run_id CASCADE、tree_content_hash、inputs_norm、node_desc、node_type、tool_calls JSON、decision、created_at + 匹配组索引）；单测断言表结构与级联
- [ ] 1.2 修正 `_build_leaf_result` 使 `LeafTrace.llm_input["description"]` 记录**替换后**描述；同步更新既有提示词/回溯回归测试
- [ ] 1.3 `RunService._finalize` 成功路径采集：经 `engine.get_exec_state` 取含 `llm_trace` 的 NodeReport，逐成功叶子蒸馏入库；单测覆盖整树失败不采集、整树成功逐叶采集
- [ ] 1.4 蒸馏工具：只留 `success=True` 调用序列（function + 关键参数 + 结果摘要截断）+ 决策，**去 ref 化**（ref 编号/坐标弱化为目标元素描述），剔除推理/失败尝试/截图/时间戳；单测覆盖去 ref 化

## 2. 匹配查询与注入

- [ ] 2.1 `RunConfig`/`LeafContext` 新增 `experience_lookup` 回调字段，`make_default_leaf_executor` 透传；`EngineService.run` 增加可选 `experience_lookup` 参数（Mock 记录不执行）；单测断言透传
- [ ] 2.2 `build_user_message` 支持可选 `reference` 段渲染（含"仅供参考，以当前语义图为准；与当前状态不符时忽略"声明）；单测覆盖渲染与 `None` 不渲染
- [ ] 2.3 查询闭包：三钥匙（hash + inputs_norm + node_desc）+ `ORDER BY created_at DESC LIMIT 1`；`execute_leaf` 在替换后调 `experience_lookup` 注入参考段；单测覆盖命中注入与未命中/关闭不变

## 3. 老化与配置

- [ ] 3.1 老化清理：采集后按匹配组保留最近 N 条、删除超出；单测覆盖超 N 删最旧、未超不删
- [ ] 3.2 配置 `experience_feedback`（默认 true）+ `experience_retention`（默认 5）入 `autobranch.config.json`；关闭路径不采集不注入；单测覆盖默认值与关闭行为

## 4. 验证与文档

- [ ] 4.1 mock LLM 集成/E2E：成功 run 采集经验 → 同结构同入参重跑断言参考段进入 prompt（mock 断言）；失败 run 不采集
- [ ] 4.2 实机对比实验（尽力运行）：同树重跑注入经验前后成功率对比，记录结果
- [ ] 4.3 更新 `docs/contract.md` §5.7.2 与 `docs/specs/M6-leaf-agent.md`、M8 相关章节；`ruff` 通过
- [ ] 4.4 全量验证：`pytest`、前端 `npm run lint/typecheck/test`、`npm run test:e2e` 全绿；按 AGENTS.md 提交并推送（中文提交信息）