## ADDED Requirements

### Requirement: 两级能力选择执行

Action / Condition 叶子节点的 agent 式执行 SHALL 支持两级能力选择：① 向 LLM 提供能力概览与框架工具 `use_capability`；② LLM 选能力后引擎加载该插件（`init`）并将其函数追加进工具集，供 LLM 细选调用。叶子执行 SHALL 支持一次执行内多轮、多能力（能力可中途追加）。系统 SHALL NOT 在叶子执行前强制预取语义图；改为在提示词中强调"操作/判断前先调用 `semantic_graph` 获取最新语义图"，由 LLM 自主决定。

#### Scenario: 叶子加载能力并调用其函数
- **WHEN** Action 执行时 LLM 调用 `use_capability("browser")` 后调用 `open`
- **THEN** 浏览器插件被加载、`open` 被调用，结果回填给 LLM

#### Scenario: 一个叶子使用多能力
- **WHEN** 某叶子先加载浏览器打开页面、再加载计算能力运算
- **THEN** 两次能力加载与调用在同一叶子执行内完成

#### Scenario: 无强制语义图预取
- **WHEN** 执行一个纯计算叶子（不涉及浏览器）
- **THEN** 不预取语义图，零浏览器开销

### Requirement: 变量写入落笔

叶子执行器 SHALL 负责变量写入落笔：当 LLM 调用**产出型工具**（声明了单一变量目标参数）时，执行器 SHALL 拆出目标参数、调用插件函数、把返回值写入当前帧的目标变量；插件函数 SHALL NOT 直接写变量空间。目标变量 SHALL 在节点的 `[[set]]` 声明集内（= Action / Condition 描述文本中 `[[set:...]]` 标注的变量集合）；多返回值映射仅经 FunctionCall 节点 `returns` 完成。

#### Scenario: 产出型工具返回值写入变量
- **WHEN** LLM 调用产出型工具（如 `extract(ref, target=结果)`）
- **THEN** 执行器拆出 `target`、调用插件函数、把返回值写入 `结果` 变量

#### Scenario: 目标未声明被拒绝
- **WHEN** 产出型工具的目标变量不在节点 `[[set]]` 声明集内
- **THEN** 执行器拒绝写入并返回错误结果给 LLM

### Requirement: 报告信息随返回值产出

叶子执行 SHALL 把插件函数返回值中携带的报告附加信息（结构化）写入报告（经统一 reporting 接口），插件 SHALL NOT 直接调用报告器。

#### Scenario: 插件附加报告信息
- **WHEN** 插件函数返回值含报告附加信息
- **THEN** 叶子执行器将其写入报告，渲染时按来源展示
