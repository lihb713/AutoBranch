# schema-namespace Specification

## Purpose

提供行为树变量命名空间（schema）机制：每个块实例拥有独立命名空间帧，管理变量读写、传参、返回值、配置参数继承与类型校验，作为确定性信息流层的纯逻辑核心保障。

## Requirements

### Requirement: 帧模型——块引用产生独立命名空间

系统 SHALL 在每次块引用时创建一个独立的 schema 帧（命名空间），帧按调用链形成层级路径；不同帧的同名变量互不冲突。

#### Scenario: 同名变量互不冲突

- **WHEN** 流程引用两次同一命名块，两次调用分别向各自帧写入同名变量 username
- **THEN** 两个帧中的 username 各自独立存储，第二次写入不覆盖第一次

#### Scenario: 嵌套调用形成层级帧路径

- **WHEN** 主流程 T 引用登录块 A，登录块 A 内部引用输入框块 A'
- **THEN** 系统为 T、A、A' 分别建立帧，路径依次为 T/、T/登录/、T/登录/输入框/
### Requirement: 严格作用域——只读写自己的帧（单段寻址）

每个块实例的读写 SHALL 严格限定在自己的 schema 帧内，用户层为**裸变量名**（ASCII 标识符）单段；直接子块、祖先、兄弟、孙子帧一律不可见，越权访问必须被拒绝并产生校验错误。跨帧传参/接收输出经 ref 的 `args`/`returns`，不通过帧路径读写。

#### Scenario: 写自己的 schema 合法

- **WHEN** 块对其自身执行 `NewParam.amount` 写入声明
- **THEN** 写入成功，变量存入该块自己的帧

#### Scenario: ref args 注入子块帧

- **WHEN** 主流程 T 经 ref 的 `args` 将输入参数注入直接子块登录的帧
- **THEN** 变量存入登录块的帧（由 M7 `_tick_ref` 在 `enter_block` 后写入子帧 `this/<形参名>`）

#### Scenario: 越权写祖先帧被拒绝

- **WHEN** 子块对其祖先的路径执行写入
- **THEN** 系统拒绝该写入并报告越权校验错误

#### Scenario: 越权写兄弟帧被拒绝

- **WHEN** 块对同层兄弟块的路径执行写入
- **THEN** 系统拒绝该写入并报告越权校验错误

#### Scenario: 越权写孙子帧被拒绝

- **WHEN** 块对其孙子的路径执行写入（跨帧多段路径）
- **THEN** 系统拒绝该写入并报告越权校验错误

#### Scenario: 越权读祖先/兄弟/孙子帧被拒绝

- **WHEN** 块对祖先、兄弟或孙子帧的路径执行读取
- **THEN** 系统拒绝该读取并报告越权校验错误
### Requirement: 变量路径读写

变量 SHALL 以裸变量名读写：写入使用 `NewParam.xxx[:类型]`，读取使用 `Param.xxx`；用户层为 ASCII 裸变量名单段，跨块传参/接收输出经 ref 的 `args`/`returns`（旧语法 `[[get]]`/`[[set]]`/`this/` 已废弃）。

#### Scenario: 路径写入与读取

- **WHEN** 块执行 `NewParam.amount` 写入金额值，随后以 `Param.amount` 读取
- **THEN** 读取结果等于写入的金额值

#### Scenario: 读取未定义变量

- **WHEN** 块读取自身帧中尚未写入的路径
- **THEN** 系统返回空值（不产生越权错误）
### Requirement: 传参逐层传递

父块 SHALL 经 ref `args` 将输入参数注入被引用子块（M7 `_tick_ref`：父帧求值实参 → coerce → `enter_block` 建子帧并写入 `this/<形参名>`）；要传给孙块必须逐层转发，每层只处理自己的直接子块。

#### Scenario: 父块写直接子块传参

- **WHEN** 主流程 T 经 ref `args` 将用户名注入直接子块登录的帧
- **THEN** 登录块以 `Param.username` 读取到该值

#### Scenario: 逐层转发到孙块

- **WHEN** 登录块需要向输入框块传值，经 ref `args` 将值注入输入框块的帧
- **THEN** 输入框块以 `Param.value` 读取到该值，且主流程 T 无法直接写入或读取该孙级路径
### Requirement: 取子块返回值

调用方 SHALL 经 ref `returns` 获取子块返回值：M7 `_tick_ref` 在子块 SUCCESS 后读子帧输出（`this/<输出名>`）并按 `returns` 映射写入父帧；帧数据保留至运行结束（供黑板上报），激活帧控制访问。

#### Scenario: 经 returns 回收取返回值

- **WHEN** 导出块完成后经 ref `returns` 将输出注入主流程 T 的帧
- **THEN** T 读取到的结果等于导出块写入的输出
### Requirement: 配置参数继承

配置参数（timeout/retry 等）SHALL 按「自己的 schema → 向上找最近祖先 → 全局默认」三级查找；业务变量不得向上查找，必须显式指明读写路径。

#### Scenario: 块自身配置优先

- **WHEN** 块自身的帧定义了配置参数 timeout，其祖先帧也定义了 timeout
- **THEN** 解析结果取该块自身定义的值

#### Scenario: 向上找最近祖先

- **WHEN** 块自身的帧未定义 timeout，但其最近祖先定义了
- **THEN** 解析结果取最近祖先的值

#### Scenario: 全局默认兜底

- **WHEN** 块自身及其所有祖先均未定义 timeout
- **THEN** 解析结果取工具配置注入根级帧的全局默认值

#### Scenario: 业务变量不向上查找

- **WHEN** 块读取自身帧中未定义的业务变量，而祖先帧存在同名业务变量
- **THEN** 读取返回空值，不产生祖先帧的值
### Requirement: 类型契约

创建变量 SHALL 声明类型（`TYPE_REGISTRY` token 之一：`str`、`int`、`float`、`bool`、`object`）；类型即真实存储类型，`set` 标注驱动的 `coerce` SHALL 把网页提取值转成声明类型后存储；写入与提取时系统 SHALL 强校验类型（`isinstance`），类型不匹配或转换失败导致断言失败并终止流程。`object` 为**泛型对象类型**——不校验（任意对象值），呈现用 `str(value)`（由对象类型的 `__str__` 定义），用于承载插件对象（页面对象 / 会话 / 文件句柄…）；引擎 SHALL 记录其实际类型（来自产出函数声明的返回类型）供黑板/报告展示。`object` SHALL 接受任意对象值（不校验具体类型）；对象在报告 / 黑板中按 `repr` 截断展示（防超长）。语义类型（金额/订单号/URL/日期 等）不占类型位，本质为 str/float 等基础类型。

#### Scenario: 合法类型值写入成功

- **WHEN** 块声明变量类型为 `float` 并写入合法数值
- **THEN** 写入成功且校验通过

#### Scenario: 泛型对象值写入

- **WHEN** 块声明变量类型为 `object` 并写入插件对象（页面对象 / 会话 / 文件句柄）
- **THEN** 写入成功（不校验具体类型），黑板/报告以 `str(value)` 呈现，并记录实际类型

#### Scenario: 非法类型值写入被拒绝

- **WHEN** 块声明变量类型为 `float` 并写入非数值文本
- **THEN** 系统拒绝写入并触发断言失败，终止当前流程

#### Scenario: 提取时类型转换与校验

- **WHEN** 块读取声明为 `float` 的变量，而其存储值不符合 float 类型（如无法转换的文本）
- **THEN** 系统在提取/写入时触发断言失败，终止当前流程

#### Scenario: 声明类型时 coerce 转换

- **WHEN** 目标变量已声明类型（非空 token）且提取值可转换（如 `"42"` 配 `int`）
- **THEN** 系统 coerce 后存储真实 Python 类型（int 42），而非原样存字符串
