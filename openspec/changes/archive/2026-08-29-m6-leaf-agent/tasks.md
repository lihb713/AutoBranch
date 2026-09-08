## 1. 数据契约与接口定义

- [x] 1.1 定义 `ToolCallRecord` 数据结构（函数名、参数、工具结果、时间戳），序列化/反序列化支持，验证：对应 dataclass 的单元测试通过（`pytest`）
- [x] 1.2 定义 `LeafResult` 与 `LeafTrace` 数据结构（`status`/`bool_value`/`error_source`/`trace` 及 `llm_input`/`llm_reasoning`/`calls`/`terminator`），字段齐全性测试通过，验证：数据契约单元测试覆盖所有字段
- [x] 1.3 定义 `execute_leaf(node, ctx)` 入口签名，判定 Action 与 Condition 节点类型并分派执行路径，验证：节点类型分派的单元测试通过

## 2. 引擎驱动循环

- [x] 2.1 实现 agent 驱动循环：构建 M0 会话（系统提示词 + 节点描述 + 当前语义图 + M5 引擎函数工具集），循环调用直至最终回答或终止，验证：mock LLM 桩返回预置工具调用序列时循环按预期驱动（`pytest`）
- [x] 2.2 实现工具调用执行与回填：识别 LLM 返回的工具调用 → 经 M5 `EngineFunctions` 执行 → 将 `OpResult` 作为工具结果回填会话，验证：mock M5 返回固定 `OpResult` 时回填正确的单元测试通过
- [x] 2.3 实现最终回答解析：将 LLM 最终回答解析为 Action 的 `status` 与 Condition 的 `bool_value`，验证：Action/Condition 最终结果解析单元测试通过
- [x] 2.4 实现追踪数据累积：每轮记录 LLM 推理过程与 `ToolCallRecord`，最终填充 `LeafTrace`，验证：追踪数据完整性测试断言 `calls` 序列与触发条件齐全

## 3. 终止条件

- [x] 3.1 实现 LLM 对话轮数上限检测（默认 10 轮），触发即终止叶子并记录 `terminator`，验证：构造超轮数 mock 序列，测试断言叶子终止且 `error_source="llm"`
- [x] 3.2 实现连续无进展检测（对连续多轮的调用/结果做指纹比较，结果未变或重复相同调用），验证：构造重复相同调用的 mock 序列，测试断言按无进展终止
- [x] 3.3 实现单叶子执行超时检测（墙钟计时，纳入全局 timeout），验证：mock 慢 LLM 响应，测试断言超时终止并记录触发条件
- [x] 3.4 验证定位终止作为叶子终止的子集被统一覆盖（§9.7：定位轮数上限、连续 2 轮相同判断），编写定位场景终止测试，验证：定位场景测试断言触发后叶子按 LLM 侧失败结束

## 4. Action 与 Condition 执行

- [x] 4.1 实现 Action 执行路径：节点描述 + 语义图 → LLM 自主调用引擎函数 → 返回成功/失败，验证：mock 场景下 LLM 决策序列与最终 `status` 的测试通过
- [x] 4.2 实现 Condition 执行路径：节点描述 + 语义图 → LLM 自主判断 → 返回确定布尔值，推理期间引擎不介入，验证：Condition 布尔结果测试通过
- [x] 4.3 实现提示词模板装配（固定模板：系统提示词 + 节点描述 + 语义图，带版本号），验证：固定输入下提示词渲染结果一致，提示词渲染测试通过

## 5. 错误边界与分类

- [x] 5.1 实现函数失败回传：`OpResult(ok=False)` 作为工具结果回传 LLM 由其自行修正，引擎只统计轮数不判断重试，验证：mock 函数失败后 LLM 修正并继续的决策序列测试通过
- [x] 5.2 实现程序侧致命错误处理：捕获 M5 抛出的 `FatalBrowserError` → 终止整个流程并分类为程序侧失败，验证：致命错误分流测试断言 `error_source="program"` 且流程终止
- [x] 5.3 实现错误来源默认分类：除程序侧致命错误外，其余失败（含全部终止）一律分类为 `"llm"`，验证：错误分类测试覆盖 LLM 侧与程序侧两类边界

## 6. 测试与回归

- [x] 6.1 编写 mock M0/M5 的 agent 决策测试集：mock 固定响应 LLM 桩 + mock `EngineFunctions`，覆盖 Action/Condition 决策序列与多轮定位（多次调用 semantic_graph 缩小/放大），验证：`pytest` 全部通过
- [x] 6.2 编写终止条件与错误分流测试集（轮数超限/无进展/超时/LLM 侧与程序侧分流），验证：`pytest` 相应用例通过
- [x] 6.3 编写提示词回归测试：固定输入 → 记录 LLM 决策 → 后续运行对比，防止决策漂移，验证：回归测试命令输出无差异
- [x] 6.4 编写 mock M5 下串联冒烟测试：Action + Condition 叶子完整执行并输出齐全的 `LeafResult`/`LeafTrace`，验证：冒烟脚本断言所有结果与追踪字段齐全
- [x] 6.5 同步更新 `docs/contract.md` 与 `docs/specs/M6-leaf-agent.md`，使其与实现的接口与行为一致，验证：文档评审确认与代码契约一致