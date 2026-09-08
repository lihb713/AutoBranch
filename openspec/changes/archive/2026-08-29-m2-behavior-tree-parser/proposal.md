## Why

M2 行为树文档解析器是 WebOps 书写层与执行层的**唯一转换点**：用户书写的行为树文档（yaml/dict）必须在此确定性解析为仅含基础节点的内部行为树对象，复合节点展开、块引用解析、schema 绑定声明提取都发生在这里。目前该模块仅有 `docs/specs/M2-behavior-tree-parser.md` 模块说明，尚无 OpenSpec 规格化需求与可执行的实现任务，导致阶段 1 无法以可验收的方式落地，也阻塞了依赖它的 M3、M7、M9b。

## What Changes

- 新增 capability `behavior-tree-parser`，覆盖行为树文档解析的全部行为契约（新 capability，写入 `specs/behavior-tree-parser/spec.md`）。
- 定义解析入口与输出契约：`parse(doc, ref_resolver) -> ParseResult`，输出纯基础节点行为树、块声明表、清晰度校验报告。
- 定义基础节点模型（Action / Condition / Sequence / Selector / Repeat / Finish）作为展开的最终形态。
- 明确复合节点展开语义并作为可测试需求：Step=Sequence(Action+Condition)、Branch=Action+Selector、LoopUntil/Retry=Repeat 两模式、IfThenElse=Selector。
- 定义块引用解析需求（this/文档名/块名、跨文档整树引用）与 schema 绑定声明提取需求。
- 定义配置参数覆盖声明识别需求（块 schema 下覆盖 timeout/retry 等，全局默认不写在文档中）。
- 定义清晰度校验需求（结构合法、展开后合法、引用存在、循环有上界、变量契约一致、可定位、有验证条件、谓词可校验）及失败时返回可读错误清单的行为。
- 建立测试策略基线：纯函数表驱动、复合节点展开、校验反例矩阵、跨文档引用。

## Capabilities

### New Capabilities
- `behavior-tree-parser`: 将行为树文档（yaml/dict）解析为仅含基础节点的内部行为树对象，展开复合节点、解析块引用、提取 schema 绑定声明、识别配置参数覆盖，并对文档执行清晰度校验。

### Modified Capabilities
- 无（`openspec/specs/` 下尚无既有 capability）。

## Impact

- 引擎层（Python）新增解析模块，纯逻辑、无外部运行时依赖（不依赖 LLM、不依赖浏览器）。
- 供 M7 编排器执行解析后的行为树对象；供 M9b 后端在保存/执行前调用校验；供 M3 以解析输出的块声明建立 schema 命名空间。
- 同步维护 `docs/contract.md` §4/§4.3/§4.4 与 §5.7.3/§5.7.4/§5.7.5 及 `docs/specs/M2-behavior-tree-parser.md` 的一致性（文档更新，不改变既有行为契约）。