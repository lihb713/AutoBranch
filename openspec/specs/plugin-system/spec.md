# plugin-system Specification

## Purpose

提供可插拔的能力框架：插件注册、懒装配、两级能力选择、统一分发与报告接口，使行为树叶子能调用任意能力（浏览器 / 计算 / SSH / 文件…），而引擎核心不感知具体能力。

## Requirements

### Requirement: 插件定义与显式注册

系统 SHALL 以「插件类」定义能力：`name`、`description`（能力说明）、`function_defs()`（结构化函数定义：名字 / 说明 / 参数 / 多返回值 / 变量目标参数 / 实现）、`init(runtime)`（初始化该插件的公共资源）、`call(name, args)`（分发到具体函数）。函数实现 SHALL 以 `@engine_function` 装饰器显式注册；函数标识 SHALL 为**全名 `插件名.函数名`**（如 `compute.add`），注册后 SHALL 以全名作为注册表键与查找键。**同一插件内函数名 SHALL 唯一**（重名注册拒绝）；**跨插件允许同名函数**（以全名区分，不视为冲突）。对 LLM 暴露的工具名 SHALL 为转义全名（`.` → `__`，如 `compute__add`；多数 OpenAI 兼容 API 拒绝含点号工具名），分发时按转义名反查回全名；同一插件重复注册视为重载（幂等覆盖）。`function_defs()` 返回的函数元数据（说明 / 参数 / 多返回值 / 变量目标参数）SHALL 在注册时与实现函数校验匹配，不一致视为注册错误。

#### Scenario: 插件注册其函数
- **WHEN** 插件被加载
- **THEN** 仅其显式标注（`@engine_function`）的函数进入注册表（键为全名 `插件名.函数名`），其余函数 / 类不注册

#### Scenario: 跨插件同名函数共存
- **WHEN** 两个不同插件分别注册同名函数（如 `compute.add` 与 `mylib.add`）
- **THEN** 两者都以全名为键共存于注册表，可通过全名分别调用，不视为冲突

#### Scenario: 同插件内重名拒绝
- **WHEN** 同一插件注册两个同名函数
- **THEN** 注册失败并报告重名

#### Scenario: 插件描述供能力概览
- **WHEN** 生成能力概览
- **THEN** 使用各插件的 `description` 生成概览文本
### Requirement: 两级能力选择

系统 SHALL 支持两级能力选择：① 向 LLM 提供「能力概览」与框架工具 `use_capability(name)`（属插件框架，不属任何具体插件）；② LLM 调用 `use_capability` 后，引擎初始化该插件（`init`）并将其函数追加进工具集，供 LLM 细选调用。选能力 SHALL 复用现有工具调用机制，不引入新的 LLM 输出协议。

#### Scenario: LLM 选能力并加载
- **WHEN** LLM 调用 `use_capability("browser")`
- **THEN** 引擎初始化浏览器插件，其函数进入可用工具集

#### Scenario: 选能力复用工具调用
- **WHEN** LLM 输出 `use_capability` 调用
- **THEN** 按普通工具调用处理，最终结果解析逻辑不变
### Requirement: 懒装配

系统 SHALL 在调用分发时懒装配插件：目标插件未初始化则调用其 `init(runtime)`；重资源（如浏览器）在单次运行内首次用到才启动、运行结束统一释放；「运行结束」指单次行为树执行完成（含失败 / 异常提前终止），释放逻辑 SHALL 保证提前终止时仍执行。

#### Scenario: 重资源按需启动
- **WHEN** 行为树首次调用某重资源插件的函数
- **THEN** 引擎装配该插件依赖并启动资源

#### Scenario: 未加载函数被直接调用
- **WHEN** LLM 调用一个属于未加载插件的函数
- **THEN** 引擎返回错误结果（提示需先加载该插件），不中断程序；该错误结果计入连续无进展轮数，由引擎兜底终止条件终止
### Requirement: 统一分发与产出型工具

系统 SHALL 提供统一分发：按**全名**定位所属插件 → 懒装配 → 调用（向插件传递裸函数名）→ 对产出型工具（`FunctionDef` 声明了变量目标参数 `output_param`）由引擎把返回值写入目标变量（引擎落笔，插件不接触变量空间）。函数全名 SHALL 在注册表内唯一，同一插件内重名注册 SHALL 被拒绝并报错；跨插件同名 SHALL 允许。产出型工具 SHALL 声明**单一**变量目标参数（对应单一返回值）；多返回值映射 SHALL 仅经 FunctionCall 节点 `returns` 完成。

#### Scenario: 产出型工具返回值落笔
- **WHEN** 调用产出型工具（声明了变量目标参数）
- **THEN** 引擎拆出目标参数、调用插件函数、把返回值写入该变量

#### Scenario: 非产出型工具
- **WHEN** 调用未声明变量目标的工具
- **THEN** 仅执行、不写变量

#### Scenario: 全名分发到所属插件
- **WHEN** 以全名 `compute.add` 调用函数
- **THEN** 引擎按全名定位 `compute` 插件（必要时懒装配）并以其裸函数名调用实现
### Requirement: 统一 reporting 接口

系统 SHALL 提供统一的报告写入接口：插件函数通过**返回值**携带报告附加信息（结构化），引擎落笔写入报告（按来源分组）；插件不直接调用报告器。

#### Scenario: 插件附加报告信息
- **WHEN** 插件函数返回值含报告附加信息
- **THEN** 引擎将其写入报告，渲染时按来源展示
### Requirement: 插件来源与组织

系统 SHALL 从两处加载插件：**预置插件**（文件系统 `plugins/` 下的包，启动扫描 + `import`，可依赖 `common` 共享库与三方库）；**用户自定义插件**（源码存数据库，`compile + exec` 加载，仅用 Python 标准库）。`common` SHALL 为共享库而非插件——不注册函数、不对 LLM 暴露。系统 SHALL NOT 提供依赖自动识别 / 安装。单插件加载 / 编译失败（如语法错误、`exec` 异常）SHALL 标记该插件为「加载失败」（记录错误、不注册其函数），不中断其他插件加载；失败状态经插件 API 可见。

#### Scenario: 预置插件启动加载
- **WHEN** 引擎启动
- **THEN** 扫描 `plugins/` 子包（排除 `common`）并 `import` 注册

#### Scenario: 自定义插件从数据库加载
- **WHEN** 加载用户自定义插件
- **THEN** 从数据库读源码，`compile + exec`（注入注册器）注册其函数

#### Scenario: 自定义插件约束
- **WHEN** 校验用户自定义插件
- **THEN** 拒绝非标准库 import、引用其他插件或 `common`
### Requirement: 多轮与多能力

系统 SHALL 支持单个叶子在一次执行内多轮交互并使用多个能力：能力可中途追加，工具集随加载增长。

#### Scenario: 一个 Action 使用多能力
- **WHEN** 某 Action 先加载浏览器打开页面、再加载计算能力运算
- **THEN** 两次能力加载与函数调用在同一叶子执行内完成
