# M3 插件框架（Plugin System）Spec

> 原 **M5 引擎函数层** 演化为插件框架；浏览器/计算/SSH/文件 等能力全部插件化。

## Purpose

提供可插拔的能力框架：插件注册、懒装配、两级能力选择、统一分发与报告接口，使行为树叶子能调用任意能力（浏览器 / 计算 / SSH / 文件…），而引擎核心不感知具体能力。

## Requirements

### 插件定义与显式注册

系统 SHALL 以「插件类」定义能力：`name` / `description` / `function_defs()`（结构化 `FunctionDef`：名字 / 说明 / 参数 / 多返回值 / 变量目标参数 / 实现）/ `init(runtime)` / `call(name, args)`。函数实现以 `@engine_function` 装饰器显式注册（函数名即插件内注册名），未标注不注册；`function_defs()` 元数据在注册时与实现函数校验匹配。**函数标识为全名 `插件名.函数名`**（如 `compute.add`），注册表键 / 查找 / 分发均用全名；对 LLM 暴露的**工具名为转义全名**（`.`→`__`，如 `compute__add`，多数 OpenAI 兼容 API 拒绝含点号工具名），分发时反查回全名。

- 场景：仅 `@engine_function` 标注的函数进入注册表（键为全名）。
- 场景：同一插件内函数名唯一（重名去重）；**跨插件允许同名**（如 `compute.sort` 与 `mylib.sort` 共存）；同一插件重复注册视为重载（幂等覆盖）。

### 两级能力选择

① 向 LLM 提供能力概览 + 框架工具 `use_capability(name)`（属框架，不属具体插件）；② LLM 选能力后引擎 `init` 插件、其函数追加进工具集供细选。复用 `tool_calls`，无新输出协议。

- 场景：`use_capability("browser")` 后浏览器函数进入工具集。

### 懒装配

调用分发时懒装配：插件未 `init` 则初始化；重资源 run 内首次用到才启动、运行结束（含失败/异常提前终止）统一释放（finally 保证）。

- 场景：纯计算行为树零浏览器开销。
- 场景：未加载插件的函数被直接调用 → 错误结果（不中断，计入连续无进展轮数）。

### 统一分发与产出型工具

按函数名定位插件 → 懒装配 → 调用。产出型工具（`FunctionDef.output_param` 声明单一变量目标参数）由引擎落笔写变量（插件只返回值、不接触变量空间）；多返回值仅经 FunctionCall `returns` 完成。

### 统一 reporting 接口

插件函数经**返回值**携带报告附加信息（`FunctionResult.report`），引擎落笔写入报告（按来源分组）；插件不直接调用报告器。

### 插件来源与组织

- 预置插件：文件系统 `autobranch/plugins/` 包（工具的一部分），启动扫描 + import；可依赖 `common` 共享库 + 三方库。
- 用户自定义插件：源码存 DB，`compile + exec`（注入注册器）加载；仅标准库，不 import 其他插件 / `common` / 三方库。
- `common` 为共享库（非插件，不注册、不对 LLM 暴露）。
- 单插件加载/编译失败 → 标记「加载失败」，不中断其他插件；失败状态经插件 API 可见。
- 引擎不做依赖自动识别/安装。

### 多轮多能力

单个叶子一次执行内可多轮交互、使用多能力（工具集随加载增长）。

## 关键实现

- `autobranch/plugin_system/`：`defs.py`（FunctionDef/FunctionResult/PluginBase/@engine_function）、`registry.py`（PluginRegistry：注册/懒装配/分发/查询）、`loader.py`（预置扫描 + DB 源码加载 + 校验）、`capability.py`（use_capability/能力概览）、`reporting.py`、`runtime.py`（PluginRuntime）。
- **预置插件位于 `autobranch/plugins/`**（工具的一部分）：`common` 共享库 + `browser`（自包含驱动/语义图）/ `compute` / `ssh` / `file`。