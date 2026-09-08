## Why

M4 语义图生成是 WebOps 页面理解能力的核心：它把 M1 爬取的原始 DOM 加工成语义图，供 LLM 在叶子执行中定位、提取与断言（§7/§8）。目前该模块仅有 `docs/specs/M4-semantic-graph.md` 模块说明，尚无 OpenSpec 规格化需求与可执行实现任务，导致依赖它的 M5/M6/M7 无法以可验收的方式落地，阶段 2 因此被阻塞。

## What Changes

- 新增 capability `semantic-graph`，覆盖语义图生成的全部行为契约（新 capability，写入 `specs/semantic-graph/spec.md`）。
- 定义两阶段生成流水线：**程序化阶段**（DOM 爬取 + 结构富集 + 几何计算 + 程序化值实时读取，纯程序）与 **LLM 填充阶段**（每个元素 purpose + related-to 关联打分与理由），每次调用两阶段都执行。
- 定义候选元素筛选规则：可交互 + 携带文本的元素必进、语义容器（form/table/dialog/nav/section/ul...）作层级骨架（REGION）、纯结构 div/span 只用于确定归属、隐藏/零尺寸/aria-hidden 始终剔除。
- 定义语义图对象模型契约：Graph / Region / Element / Edge / Change，元素统一为单一节点（文本为 state.text 属性）、三种边（part-of / value-of / related-to）、ref 映射表（引用解析归引擎、确定性）。
- 定义统一接口 `semantic_graph(范围, LOD)`：范围控制广度、LOD 四维参数组合（深度/广度/属性/关联）划分 LOD-0~3，**每次调用完整生成、无缓存**，token 预算超限可检测。
- 定义序列化契约（§7.6）：层次树文本，part-of 编码为缩进层级、兄弟按视觉顺序、value-of 并列、related-to 括号标注带分数，ref 映射表正确。
- 明确第一版范围边界：不处理 iframe、懒加载/虚拟滚动/动态渲染、Canvas 渲染页面。
- 建立测试策略基线：程序化阶段独立测试（HTML fixture）、LLM 填充 mock 测试、LOD 分级测试、序列化快照测试、集成冒烟（可选）。

## Capabilities

### New Capabilities
- `semantic-graph`: 将 M1 爬取的 DOM 快照经两阶段流水线（程序化 + LLM 填充）加工为语义图对象模型，提供 LOD 分级的 `semantic_graph(范围, LOD)` 接口与 LLM 可读的层次树序列化文本。

### Modified Capabilities
- 无（`openspec/specs/` 下尚无既有 capability）。

## Impact

- 引擎层（Python）新增语义图生成模块，依赖 M1（DOM 快照，可 mock）与 M0（LLM 填充，可 mock）。
- 供 M5 引擎函数层以 `semantic_graph` 引擎函数暴露给 LLM；M6/M7 通过 M5 间接消费。
- 新增输出结构：SemanticGraph 对象模型（Graph/Region/Element/Edge/Change）与序列化层次树文本；新增 ref 映射表。
- 同步维护 `docs/contract.md` §7（语义图内容模型）、§8（语义图生成）、§9.5（LOD 分级）与 `docs/specs/M4-semantic-graph.md` 的一致性（文档更新，不改变既有行为契约）。