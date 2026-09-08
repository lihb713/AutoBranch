## 1. 数据模型与工程骨架

- [x] 1.1 建立语义图对象模型（Graph/Region/Element/Edge/Change dataclass，含 ref 分配字段）并编写模型序列化/校验测试：`pytest` 通过，元素 id/ref 唯一性有测试覆盖
- [x] 1.2 建立模块包结构（程序化阶段、LLM 填充、接口、序列化分目录）并验证模块可导入：`python -c "import webops.m4"` 成功（实际包名 `webops.semantic_graph`，`import webops.semantic_graph` 验证通过）
- [x] 1.3 定义 DOM 快照消费契约（对齐 `docs/specs/M1-browser-driver.md` §5.4/§5.5）并提供可注入的 mock 快照夹具：编写 `tests/fixtures/` 中 HTML fixture 与快照构造器，单元测试通过

## 2. 程序化阶段（独立于 LLM）

- [x] 2.1 实现候选元素筛选规则（可交互+携带文本必进、语义容器作 REGION 骨架、纯定位 div/span 归属性、隐藏/零尺寸/aria-hidden 剔除）：用固定 HTML fixture 断言候选集/REGION 集合/过滤结果，测试通过
- [x] 2.2 实现结构富集（role 归一化、part-of 从属边、表格框架派生 value-of 边）：fixture 断言 part-of/value-of 边及 origin=structural，测试通过
- [x] 2.3 实现几何计算（bounds、可见性、阅读顺序即兄弟按视觉顺序排序）：fixture 断言 bounds 与兄弟排序，测试通过
- [x] 2.4 实现程序化值读取（value/checked/disabled/visible/text/selected/options 实时读取）：fixture 断言各状态字段与 select 选项，测试通过
- [x] 2.5 为 related-to 生成几何候选预筛（按 bounds 邻近性产出候选输入，不直接成边）：fixture 断言候选集正确，测试通过
- [x] 2.6 程序化阶段整体独立验证：`pytest`（不含集成标记）全部通过，证明不依赖 LLM 与真实浏览器

## 3. LLM 填充阶段（先 mock、后接 M0）

- [x] 3.1 定义可注入的 LLM 填充器接口（fill_purpose / score_related_to）并实现 mock 填充器：注入 mock 后生成流水线可跑通，单元测试通过
- [x] 3.2 实现 purpose 填充（LLM 为每个候选元素填充 purpose 并写入 Element）：mock 返回固定 purpose → 断言写入正确，测试通过
- [x] 3.3 实现 related-to 打分填充（LLM 基于几何候选产出分数+理由，写入 Edge）：mock 返回固定打分 → 断言边（含弱关联保留、score/reason/origin=visual）正确，测试通过
- [x] 3.4 接入真实 M0 LLM 客户端（替换 mock 为可配置实现）：`LLMSessionFiller` 经 M0 `LLMSession` + FakeTransport 驱动测试通过；`test_smoke.py`（真实 API，可选）已提供

## 4. 接口与 LOD 分级

- [x] 4.1 实现统一入口 `semantic_graph(page_ref, 范围, LOD)`，每次调用完整执行两阶段且无缓存：修改 input 值后再次调用，断言输出反映新值，测试通过
- [x] 4.2 实现范围参数（全页/指定区域 id）过滤输出：以区域调用后断言仅覆盖该区域，测试通过
- [x] 4.3 实现 LOD 四维裁剪（深度/广度/属性/关联）与 LOD-0~3 预置组合：同一页面四档 LOD 输出符合维度定义（深度/广度/属性/关联逐级增强），LOD 测试通过
- [x] 4.4 实现 token 预算超限检测（LOD+范围+序列化估算，超限报告不静默截断）：构造超预算场景断言检测触发，测试通过

## 5. 序列化与 ref 映射

- [x] 5.1 实现层次树序列化（REGION 头、元素行、文本承载元素 `purpose="text"`、状态子集渲染、part-of 缩进、value-of 并列、related-to 括号标注、兄弟视觉顺序）：序列化快照测试对比期望文本通过
- [x] 5.2 实现 ref 映射表（引擎确定性分配 ref，`[N]` ↔ 元素 id ↔ DOM 节点双向解析）：ref 解析测试通过，证明不依赖 LLM 猜测
- [x] 5.3 完整序列化示例快照（对照契约 §7.6.4 登录页/订单列表示例）：快照测试通过

## 6. 集成验收与文档同步

- [x] 6.1 集成测试（真实浏览器 + mock LLM，`pytest -m integration`）：从真实页面生成语义图并断言对象模型与序列化文本符合契约
- [x] 6.2 集成冒烟（可选，真实 M0 LLM）：`test_smoke.py` 已提供（标记 smoke，默认跳过，需 `WEB_OPS_TEST_LLM=1` 与环境配置）
- [x] 6.3 同步维护 `docs/contract.md`（§7/§8/§9.5 相关表述）与 `docs/specs/M4-semantic-graph.md`，保持与实现一致：`docs/specs/M4-semantic-graph.md` 已更新（含实现状态/接口细节/测试覆盖）；contract.md 按约定由用户统一处理，变更点见实施汇报
- [x] 6.4 全量回归：`pytest`（含 `pytest -m integration`）472 通过、3 跳过，无模块外回归；`ruff check .` 无告警