## 1. 遍历器核心骨架

- [x] 1.1 定义节点状态常量与 `RunConfig`（全局 timeout 等）数据结构，验证 `pytest` 下基础类型测试通过
- [x] 1.2 定义 `RunContext`（注入 schema 命名空间 / 报告器 / 叶子执行器 / 浏览器 context / 执行状态），提供依赖注入构造，验证单测确认各依赖可被 mock 替换
- [x] 1.3 实现基础节点统一的 `tick()` 契约（返回 SUCCESS/FAILURE，阻塞式，无 RUNNING），验证一个 `Action` 节点 mock 返回成功/失败时 tick 返回对应状态
- [x] 1.4 实现 `Engine.run(tree, blocks, config)` 入口：解析校验（M2）→ 会话初始化 → 遍历 → 返回 `RunResult`，验证 mock 树跑通并返回含两份报告的结果对象

## 2. 组合节点纯程序执行

- [x] 2.1 实现 Sequence tick：依次执行、首个 FAILURE 短路、全 SUCCESS 才 SUCCESS，验证表驱动测试覆盖"全成功/中途短路"分支且短路后后续子节点不执行
- [x] 2.2 实现 Selector tick：按顺序分流、首个 SUCCESS 短路、全 FAILURE 才 FAILURE，验证表驱动测试覆盖"首个成功分流/全失败"分支且短路后其余分支不执行
- [x] 2.3 实现 Repeat 基础循环框架：轮次计数 + `max` 上界，到达上界返回 FAILURE，验证循环次数与上界测试通过
- [x] 2.4 实现 Repeat `loop_until` 模式：每轮先 tick until 条件，满足即退、不满足才执行 body，验证"初始即满足不执行 body / 不满足时执行 body 后重判"两组场景
- [x] 2.5 实现 Repeat `retry` 模式：每轮直接 tick body，成功即退、失败重试至 `max`，验证"body 成功即退出 / body 失败重试至上限返回 FAILURE"两组场景
- [x] 2.6 组合节点全量表驱动测试：Sequence/Selector/Repeat（两种模式）各分支场景矩阵，验证全部通过

## 3. 叶子触发、失败传播与超时

- [x] 3.1 实现 Action/Condition 叶子触发：调用 M6 `execute_leaf` 接收 `LeafResult`，Condition 布尔值映射为节点状态，验证 mock 叶子返回固定结果时状态映射正确
- [x] 3.2 实现叶子追踪数据与报告联动：叶子返回的 `LeafTrace` 随节点报告记录（经 M8），验证 mock 报告器收到含追踪数据的节点报告
- [x] 3.3 实现失败传播：叶子 FAILURE 沿树向上由组合节点聚合，根统一终止并返回失败原因，验证 mock 叶子失败时整棵树按聚合规则终止且 `RunResult.failure_reason` 指向失败叶子
- [x] 3.4 实现全局超时：遍历器将生效 timeout 折算为 deadline 传给叶子，并保留 wall-clock 兜底检查，验证 mock 叶子阻塞超时后该叶子被置为 FAILURE 并沿树传播
- [x] 3.5 验证超时配置继承：块覆盖 timeout 的叶子用覆盖值、其余用全局默认，验证超时边界测试通过

## 4. schema 帧与会话初始化

- [x] 4.1 实现块引用节点：tick 进入时调用 M3 `enter_block` 建帧、退出时释放帧（无论成败），验证建帧/释放时机与帧隔离单测通过
- [x] 4.2 配置参数继承接入：叶子/块解析配置经 `resolve_config`（自身 → 祖先 → 全局默认），验证三级继承链表驱动测试通过
- [x] 4.3 会话初始化：`engine.run` 开头通过 M1 创建全新浏览器 context（无持久化），验证 mock M1 下确认每次 run 新建 context、无历史 cookie
- [x] 4.4 全局默认配置注入根级 schema，验证初始化后 `resolve_config` 兜底取到全局默认
- [x] 4.5 会话释放：遍历结束（成功/失败）统一关闭 context，验证结束时 mock M1 收到关闭调用且运行间无残留

## 5. 可查询执行状态

- [x] 5.1 实现 `ExecState`（run_id/progress/current_node/completed/finished）并挂入 RunContext，验证结构单测通过
- [x] 5.2 实现节点进入/退出时的状态更新：进入写 current_node、退出追加 completed、progress 单调推进，验证 mock 遍历下状态更新时序正确
- [x] 5.3 实现 `Engine.get_exec_state()` 返回不可变快照（线程安全读），验证执行中多次轮询返回一致且单调推进的状态
- [x] 5.4 验证运行结束后 `finished` 置位且 completed 含全部节点报告

## 6. 引擎集成与验收

- [x] 6.1 写一个跨 Sequence/Selector/Repeat/块引用/失败路径的 mock 树，验证 `engine.run` 端到端结果符合 §5.7.7 聚合规则（引擎集成冒烟，mock 叶子）
- [x] 6.2 可选：真实小行为树 + 真实浏览器跑通一次（引擎集成冒烟），验证超时、截图与报告链路在真实环境下工作
- [x] 6.3 运行 `pytest` 全量通过并核对 `docs/specs/M7-orchestrator.md` 第 6 章验收标准逐项勾选，确认 specs 各场景均有对应测试覆盖
- [x] 6.4 同步更新 `docs/contract.md`（如执行状态/入口描述有差异）与 `docs/specs/M7-orchestrator.md`，保证说明书与实现一致