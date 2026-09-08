## Why

WebOps 的确定性编排能力（契约 §5.7/§5.7.7）目前尚无任何实现：M2 已能产出内部行为树、M3 已能管理 schema 帧、M6 已能执行叶子、M8 已能记录报告，但还缺少把它们串起来的**编排器 + 遍历器**。M7 是引擎整合中枢，没有它行为树无法被实际执行，M9b 的引擎内嵌形态（§12.3）也无从谈起，因此现在落地它以打通整条引擎链路。

## What Changes

- 新增引擎入口 `engine.run(行为树, 块声明, 配置)`：解析校验后初始化会话、遍历执行、返回运行结果（§5.1）
- 新增确定性遍历器：**阻塞式遍历**，节点状态只有 SUCCESS/FAILURE（无 RUNNING），一次只执行一个节点（§5.7.7）
- 新增组合节点执行：Sequence（第一个 FAILURE 短路）、Selector（按条件分流、第一个 SUCCESS 短路）、Repeat（带上限，到达上限整体 FAILURE），**纯程序执行、零 LLM**（§5.7.7）
- 新增 Repeat 两种模式语义：LoopUntil 每轮**先判** until（页面条件）再执行、Retry 每轮**直接执行** body 后判结果，成功即退、失败重试（§4.3）
- 新增叶子节点触发：调用 M6 执行 Action/Condition，接收叶子结果（§5.7.2）
- 新增失败传播：叶子 FAILURE 沿树向上传播，由组合节点聚合，根统一决定终止 + 报告（§5.7.7）
- 新增超时：全局 timeout 在节点层面生效，单叶子超时即终止该叶子（§5.7.2.1 终止条件③）
- 新增 schema 帧管理：每次块引用建立/释放独立 schema 帧（M3），严格作用域读写（§5.7.4）
- 新增会话初始化：每次 run 创建全新浏览器 context（从 0 开始、不持久化），全局默认配置注入根级 schema（§5.9）
- 新增可查询执行状态 `ExecState`：run_id / 进度 / 当前节点 / 已完成节点报告 / 是否结束，供 M9b 轮询（§12.4）

## Capabilities

### New Capabilities
- `orchestrator`: 引擎的确定性编排与遍历中枢——阻塞式遍历 SUCCESS/FAILURE 聚合、组合节点（Sequence/Selector/Repeat）纯程序执行、叶子触发与失败传播、schema 帧生命周期、会话初始化、全局超时，以及可查询的执行状态（供 M9b 轮询），被 M9b 后端作为库内嵌调用

### Modified Capabilities
<!-- 无既有 capability 的需求发生变更，本 change 仅新增 orchestrator capability -->

## Impact

- **新增代码**：引擎编排层（对应 `docs/specs/M7-orchestrator.md` 第 5 章接口契约）——`Engine` 入口、遍历器、组合节点调度、schema 帧接入、会话初始化、`ExecState` 维护
- **依赖方**：M2（内部行为树对象 + 块声明）、M3（schema 帧管理、配置继承）、M6（叶子执行结果）、M8（报告记录）
- **被依赖方**：M9b（后端）——`engine.run()` 异步后台触发、`get_exec_state()` 轮询执行状态（§12.3/§12.4）
- **测试影响**：以 mock M6 叶子执行为主验证遍历/聚合/失败传播逻辑，不依赖真实浏览器与 LLM；组合节点采用表驱动测试覆盖各分支场景