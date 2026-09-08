## 1. 数据模型与记录接口

- [x] 1.1 定义 `NodeReport` 数据结构（node_type/node_desc/result/action_call/condition_result/timestamp/page_url/screenshot_path/llm_trace，Action/Condition/复合节点专用字段可空），并验证对其各字段进行 mock 赋值与序列化的单元测试通过
- [x] 1.2 实现 `Reporter.record_node(node_report)` 记录接口：累积节点报告，并验证 mock 多条节点报告后累积列表顺序正确
- [x] 1.3 定义 `ExecState` 数据结构（run_id/progress/current_node/completed/finished）与 `NodeInfo`，并验证其字段可被 mock 构造并查询

## 2. 截图

- [x] 2.1 实现 `Reporter.capture_screenshot(page_ref)`：调用 M1 截图能力、截图写入存储目录并返回路径，验证 mock M1 返回文件后路径正确且文件存在于存储目录
- [x] 2.2 处理截图失败：截图异常时记录失败、返回空路径且不中断，验证 mock M1 抛错时返回空路径且已记录的节点报告不受影响

## 3. 两份报告生成

- [x] 3.1 实现执行报告生成（报告①）：每节点输出节点类型/描述/结果/函数调用/判断结果/时间/URL/截图，且不含 LLM 推理，验证以 mock 节点报告构造后报告内容逐项正确
- [x] 3.2 实现回溯报告生成（报告②）：每节点输出执行详情 + LLM 输入/推理过程/决策结果（读取 `llm_trace`），且不含任何截图路径，验证 mock LeafTrace 后回溯内容完整且无截图字段
- [x] 3.3 实现 `Reporter.finalize()` 返回 `ReportBundle`（含执行报告与回溯报告），并验证基于同一组节点报告两份报告内容一致、均落盘

## 4. 执行状态

- [x] 4.1 实现执行状态维护：节点完成时 `completed` 累积、`progress`（已完成/总数）推进、`current_node` 更新、结束置 `finished`，验证节点逐个完成时状态按预期变化
- [x] 4.2 实现执行状态查询接口，验证查询返回当前进度/当前节点/已完成报告且查询动作不改变执行状态

## 5. 报告与截图持久化

- [x] 5.1 按 run_id 归组的存储布局（截图/执行报告/回溯报告文件），验证同一 run_id 下文件齐全、路径可被外部访问，不同 run_id 互不混淆

## 6. 测试与独立性验证

- [x] 6.1 mock 节点执行数据测试：构造覆盖 Action/Condition/复合节点、成功/失败的节点报告集，验证两份报告生成正确，命令：`pytest`
- [x] 6.2 截图测试：mock M1 截图，验证截图路径正确关联到对应节点报告且文件存在
- [x] 6.3 LLM 推理测试：mock LeafTrace，验证回溯报告包含 LLM 输入/推理过程/决策结果且执行报告不含推理
- [x] 6.4 执行状态测试：mock 节点完成序列，验证状态累积与进度更新正确
- [x] 6.5 独立性验证：全部测试仅 mock M1/M6/M7 数据，不启动真实浏览器与 LLM，验证 `pytest -m integration` 之外无需真实执行环境即可全绿