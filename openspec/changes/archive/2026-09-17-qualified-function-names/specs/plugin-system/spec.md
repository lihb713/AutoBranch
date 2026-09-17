## MODIFIED Requirements

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