## Purpose

语义图生成（M4）将浏览器爬取的原始 DOM 页面加工为语义图对象模型与 LLM 可读的层次树文本，供 LLM 在叶子执行中定位、提取与断言页面元素。其核心是"流程确定性、LLM 在语义字段内行使有限执行权"：程序化阶段纯程序地提供结构/几何/状态等客观事实，LLM 填充阶段为每个元素补上作用（purpose）与关联（related-to）等语义理解。

## ADDED Requirements

### Requirement: 两阶段生成流水线

语义图生成必须采用两阶段流水线：**程序化阶段**（纯程序、零 LLM，每次都跑）负责 DOM 爬取、候选元素分类与过滤、role/层级/part-of 结构富集、bounds/可见性/阅读顺序几何计算、程序化值（value/checked/disabled/visible/text/selected/options）实时读取；**LLM 填充阶段**（每次都做）负责为每个候选元素填充 purpose，并为元素间填充 related-to 关联打分与理由。两阶段必须在每次调用 `semantic_graph` 时都完整执行。

#### Scenario: 程序化阶段产出客观事实

- **WHEN** 对包含表单、输入框、按钮与纯文本元素的页面调用语义图生成
- **THEN** 输出的语义图中每个元素带有程序化读取的 role、state（含 value/checked/disabled/visible/text/selected）、options（select 时）与 bounds 字段

#### Scenario: LLM 填充阶段填充 purpose 与关联

- **WHEN** 程序化阶段完成后，对候选元素执行 LLM 填充（mock M0 返回固定 purpose 与 related-to 打分）
- **THEN** 每个候选元素被写入 LLM 返回的 purpose，元素间生成携带 score 与 reason 的 related-to 边

### Requirement: 候选元素筛选规则

系统必须按如下规则从 DOM 节点中筛选进入语义图的候选元素：① 可交互元素（input/button/a/select/textarea/checkbox/radio 等）与携带可见文本的元素必须进图，文本作为属性（state.text）记录在所属元素上、不单独成节点；② 语义容器（form/table/dialog/nav/section/fieldset/ul 等）进图作为层级骨架与区域边界（REGION）；③ 纯定位 div/span 不占独立层级，只用于通过 DOM 祖先关系确定元素归属；④ 语义容器嵌套深度由 LOD 控制；⑤ 隐藏/零尺寸/aria-hidden 的元素始终剔除。

#### Scenario: 可交互与携带文本元素必进

- **WHEN** 页面包含一个 input、一个按钮、一个 span 携带文本"¥98.00" 与一个纯定位 div
- **THEN** input、按钮与 span 都作为元素进图，span 的文本"¥98.00"记录在其 state.text 属性中，而纯定位 div 不占独立层级

#### Scenario: 语义容器形成区域骨架

- **WHEN** 页面含一个 form 与一个 nav，内部各含可交互元素
- **THEN** form 与 nav 作为 REGION 进图提供区域边界，其内部元素挂载在对应区域下（part-of 关系）

#### Scenario: 隐藏元素被过滤

- **WHEN** 页面元素被 `display:none`/`opacity:0`/`aria-hidden` 隐藏，或尺寸为零
- **THEN** 这些元素不进入语义图

### Requirement: 语义图对象模型

系统必须输出符合 §7.5 契约的语义图对象模型：**Graph**（type/version/page/regions/elements/edges/changes）、**Region**（id/ref/region_type/label/scope/bounds/child_elements）、**Element**（id/ref/role/purpose/state/options/bounds/confidence，元素统一为单一节点类型，文本为 state.text 属性）、**Edge**（type/from/to/origin/confidence/score/reason/detail）、**Change**（可选，type/node_id/summary）。元素 id 与 ref 必须唯一，ref 为 LLM 引用锚点。

#### Scenario: 图形与节点唯一标识

- **WHEN** 语义图生成完成
- **THEN** 图根含 page 信息，regions/elements/edges 数组齐全，每个元素的 id 与 ref 唯一，文本承载元素与普通元素共用同一结构且文本在 state.text 中

#### Scenario: 变化段可选

- **WHEN** 无上次快照可供对比
- **THEN** changes 列表为空（可选字段），不影响语义图结构合法性

### Requirement: 三种关联边

系统必须支持并区分三种关联边：**part-of**（结构从属，来自 DOM 树，编码为缩进层级）、**value-of**（数据归属，文本承载元素归属于某字段/列）、**related-to**（视觉语义关联，来自视觉几何，多对多、带权重）。related-to 的分数与理由由 LLM 每次生成时填充，无跨快照累积；每条边携带来源（visual/structural）与置信度（explicit/inferred/ambiguous）。

#### Scenario: part-of 反映 DOM 从属

- **WHEN** 一个按钮位于一个表格行内
- **THEN** 按钮与表格行之间生成 part-of 边，origin 为 structural

#### Scenario: related-to 反映视觉关联且为多对多

- **WHEN** span"用户名"与两个 input 相邻，与第一个强相关、与第二个弱相关
- **THEN** 生成两条 related-to 边（分数不同），弱关联（低分）也保留，origin 为 visual

#### Scenario: value-of 反映字段数据归属

- **WHEN** 表头"金额"列下的单元格文本为"¥98.00"
- **THEN** 单元格元素与金额列之间生成 value-of 边，体现其文本为该字段的值

### Requirement: 统一语义图接口与每次完整生成

系统必须提供统一接口 `semantic_graph(page_ref, 范围, LOD)`：① 每次调用都完整执行程序化阶段与 LLM 填充阶段，**无缓存、无指纹、无失效机制**；② 范围（全页/指定区域 id）控制广度维度；③ LOD（0~3）按四维参数（深度/广度/属性/关联）控制精细程度；④ 程序化值（如 input 当前值）在每次生成中实时读取；⑤ token 预算超限必须可检测。任何页面变化（含 input 值变化）都必须反映到下次调用的输出中。

#### Scenario: 每次调用完整生成且反映输入变化

- **WHEN** 同一页面第一次调用后修改 input 值，再次以相同范围与 LOD 调用
- **THEN** 第二次输出的语义图反映新 input 值，说明每次调用都重新执行程序化与 LLM 填充阶段

#### Scenario: 范围限定输出区域

- **WHEN** 以范围=表格 T1 调用 `semantic_graph`
- **THEN** 输出的语义图仅覆盖该区域及其内部元素，广度受限于范围参数

#### Scenario: token 预算超限可检测

- **WHEN** 语义图序列化文本或中间结果超出预设 token 预算
- **THEN** 系统检测并报告预算超限（可失败或提示降级），不静默返回截断的不完整语义图

### Requirement: LOD 分级

系统必须实现四维参数（深度/广度/属性/关联）组合的 LOD 分级：**LOD-0** 深度=0、广度=只含候选、属性=仅 role+名、关联=无，用于页面概览；**LOD-1** 深度=1、广度=区域、属性=含 value、关联=高分边，用于正常定位；**LOD-2** 深度=2、广度=整区域、属性=含相关文本、关联=全部分数+理由，用于复杂判断/提取；**LOD-3** 全量展开，用于疑难兜底。各级输出必须符合对应维度的定义。

#### Scenario: 各级 LOD 输出符合维度定义

- **WHEN** 对同一页面分别以 LOD-0、LOD-1、LOD-2、LOD-3 调用 `semantic_graph`
- **THEN** LOD-0 只有候选元素的 role 与名称且无关联边，LOD-1 增加 value 与高分 related-to 边，LOD-2 增加相关文本与全部分数+理由的关联，LOD-3 输出全部元素、属性与关联

### Requirement: 层次树序列化

系统必须按 §7.6 契约将语义图对象模型序列化为 LLM 可读的层次树文本：区域渲染为 `REGION <region_type> <ref> <label>`；元素渲染为 `<缩进> <role前缀> [<ref>] <purpose> [状态]`；文本承载元素渲染为 `<缩进> <role> [<ref>] <purpose>="<text>"`；part-of 编码为缩进层级；兄弟节点按视觉顺序（从左到右、从上到下）排列；related-to 以 `(related-to: <来源元素> <分数>·<推断依据>)` 括号标注；value-of 并列在所属元素行内；引擎内部字段（id/bounds 等）不进文本，confidence 仅歧义时标注。ref 必须由引擎确定性地从 ref 映射表分配，LLM 原样引用。

#### Scenario: 区域与元素序列化为层次树

- **WHEN** 序列化一个含 FORM 区域、textbox、button 与文本承载元素的语义图
- **THEN** 输出以 REGION 头开头，元素按缩进层级排列，textbox 含 value 状态，button 含 purpose，文本承载元素显示为 `purpose="text"` 形式，兄弟元素按视觉顺序排列

#### Scenario: 关联边按各自方式呈现

- **WHEN** 语义图含 part-of、value-of、related-to 三种边
- **THEN** part-of 表现为缩进层级、value-of 表现为并列字段行、related-to 以带分数的括号标注出现在目标元素行尾

#### Scenario: ref 映射表确定性

- **WHEN** LLM 在文本中引用 `[N]`
- **THEN** 引擎依据 ref 映射表确定性地将 `[N]` 映射回唯一元素 id（对应 DOM 节点），不依赖 LLM 猜测

### Requirement: 范围边界与失败语义

系统第一版必须明确不处理：跨 iframe 的语义图与操作（语义图只覆盖主文档）、懒加载/虚拟滚动/动态渲染（默认页面加载后元素就绪）。对已知限制（display:none/opacity:0/aria-hidden/视口外、Shadow DOM 层级信息可能丢失、Canvas 渲染页面、超大页面 token 压力）必须如实处理：隐藏类按筛选规则剔除，超大页面依赖蒸馏与 LOD 分级呈现。程序化阶段失败（如 DOM 爬取失败）与 LLM 填充失败必须可区分并报告。

#### Scenario: 主文档范围边界

- **WHEN** 页面内含 iframe，iframe 内有元素
- **THEN** 语义图只覆盖主文档元素，不合并 iframe 内元素

#### Scenario: 失败可区分

- **WHEN** DOM 爬取失败（程序侧失败）或 LLM 填充失败
- **THEN** 系统区分错误源并报告（程序侧失败可重试、LLM 侧失败重试无意义），不产出静默错误的不完整语义图