"""任务 5.1~5.6：清晰度校验反例矩阵（§4.4 八类，逐类验证报错）。"""

from __future__ import annotations

from parser_fixtures import (
    EXPORT_DOC as _EXPORT_DOC,
)
from parser_fixtures import (
    LOGIN_DOC as _LOGIN_DOC,
)
from parser_fixtures import (
    MAIN_DOC as _MAIN_DOC,
)
from parser_fixtures import (
    build_resolver,
    make_sources,
    parse_doc,
)

from webops.parser import ActionNode, CheckIssue, SequenceNode
from webops.parser.checks import post_expansion_checks

RESOLVER = build_resolver(*make_sources())


def _codes(result) -> set[str]:
    return {i.code for i in result.checks.issues}


# ---- 5.1 结构与展开后合法性 ----

def test_invalid_node_type_fails():
    """5.1 未定义的节点类型 → structure.unknown_node，错误可定位。"""
    result = parse_doc("坏", {"block 坏": {"Flog": "x"}}, RESOLVER)
    assert result.checks.ok is False
    issue = [i for i in result.checks.issues if i.code == "structure.unknown_node"][0]
    assert issue.message
    assert issue.loc is not None
    assert "坏" in issue.loc.path


def test_invalid_nesting_fails():
    """5.1 非法嵌套（Sequence 项非节点映射）→ structure.invalid_node。"""
    result = parse_doc("坏", {"block 坏": {"Sequence": ["纯字符串"]}}, RESOLVER)
    assert any(i.code == "structure.invalid_node" for i in result.checks.issues)


def test_two_node_keys_fails():
    """5.1 块内多个行为树节点键 → structure.invalid_flow。"""
    doc = {
        "block 坏": {
            "Sequence": [{"Action": "a"}],
            "Step": {"action": "b", "expect": "c"},
        }
    }
    result = parse_doc("坏", doc, RESOLVER)
    assert any(i.code == "structure.invalid_flow" for i in result.checks.issues)


def test_post_expansion_only_basic_nodes():
    """5.1 展开后合法性：残留非法节点 → expand.residual_composite。"""
    bad = SequenceNode(children=(object(),))
    issues = post_expansion_checks(bad)
    assert any(i.code == "expand.residual_composite" for i in issues)


def test_post_expansion_clean_passes():
    issues = post_expansion_checks(SequenceNode(children=(ActionNode("点"),)))
    assert issues == ()


# ---- 5.2 引用存在性与循环上界 ----

def test_ref_missing_raises():
    """5.2 引用不存在 → ref.missing_doc / ref.missing_block。"""
    doc = {"block 用户": {"Sequence": [{"ref": "不存在/不存在"}]}}
    result = parse_doc("用户", doc, RESOLVER)
    assert any(i.code == "ref.missing_doc" for i in result.checks.issues)
    doc2 = {"block 用户": {"Sequence": [{"ref": "登录/无此块"}]}}
    result2 = parse_doc("用户", doc2, RESOLVER)
    assert any(i.code == "ref.missing_block" for i in result2.checks.issues)


def test_loop_without_max_fails():
    """5.2 循环无上界 → repeat.max_missing。"""
    result = parse_doc(
        "坏", {"block 坏": {"LoopUntil": {"action": "点", "until": "消失"}}}, RESOLVER
    )
    assert any(i.code == "repeat.max_missing" for i in result.checks.issues)


def test_retry_without_max_fails():
    result = parse_doc(
        "坏", {"block 坏": {"Retry": {"body": {"Action": "点"}}}}, RESOLVER
    )
    assert any(i.code == "repeat.max_missing" for i in result.checks.issues)


def test_max_not_int_fails():
    result = parse_doc(
        "坏",
        {"block 坏": {"LoopUntil": {"action": "点", "until": "消失", "max": "很多次"}}},
        RESOLVER,
    )
    assert any(i.code == "repeat.max_not_int" for i in result.checks.issues)


# ---- 5.3 变量契约（作用域） ----

def test_out_of_scope_sibling_fails():
    """5.3 引用兄弟块 schema → scope.out_of_scope（指明位置）。"""
    doc = {
        "block 主流程": {"Sequence": [{"ref": "this/甲"}, {"ref": "this/乙"}]},
        "block 甲": {"Sequence": [{"Action": "读兄弟 [[get:this/乙/值]]"}]},
        "block 乙": {"Sequence": [{"Action": "动作"}]},
    }
    result = parse_doc("主流程", doc, RESOLVER)
    issues = [i for i in result.checks.issues if i.code == "scope.out_of_scope"]
    assert issues
    assert "乙" in issues[0].message


def test_out_of_scope_grandchild_fails():
    """5.3 引用孙子 schema（三 segment）→ scope.out_of_scope。"""
    doc = {
        "block 主流程": {"Sequence": [{"ref": "this/甲"}]},
        "block 甲": {
            "Sequence": [
                {"ref": "this/乙"},
                {"Action": "读孙子 [[get:this/乙/内/深]]"},
            ]
        },
        "block 乙": {"Sequence": [{"Action": "动作"}]},
    }
    result = parse_doc("主流程", doc, RESOLVER)
    issues = [i for i in result.checks.issues if i.code == "scope.out_of_scope"]
    assert issues
    assert "this/乙/内/深" in issues[0].message


def test_in_scope_functional_ref_passes():
    """5.3 函数式传参（returns 目标单段 this/变量）→ 通过。"""
    result = parse_doc("导出", _EXPORT_DOC, RESOLVER)
    assert not any(i.code == "scope.out_of_scope" for i in result.checks.issues)


def test_own_schema_passes():
    """5.3 读写自己的 schema → 通过。"""
    result = parse_doc("登录", _LOGIN_DOC, RESOLVER)
    assert result.checks.ok, result.checks.issues


# ---- 5.3b 单段作用域与 output 全赋值（函数式传参） ----

def test_single_segment_rejects_subblock_path():
    """5.3b 跨帧寻址 this/子块/变量 → scope.out_of_scope（单段作用域）。"""
    doc = {
        "block 主流程": {
            "Sequence": [{"Action": "读子块输出 [[get:this/导出/报告]]"}]
        }
    }
    result = parse_doc("主流程", doc, RESOLVER)
    issues = [i for i in result.checks.issues if i.code == "scope.out_of_scope"]
    assert issues
    assert "this/导出/报告" in issues[0].message


def test_output_not_set_when_missing_assignment():
    """5.3b 块声明输出但块内无赋值点 → ref.output_not_set。"""
    doc = {
        "block 甲": {
            "outputs": "p1, p2",
            "Sequence": [{"Action": "提取 [[set:this/p1]]"}],
        }
    }
    result = parse_doc("甲", doc, RESOLVER)
    issues = [i for i in result.checks.issues if i.code == "ref.output_not_set"]
    assert issues
    assert any("p2" in i.message for i in issues)
    assert not any("p1" in i.message for i in issues)


def test_output_assigned_by_ref_returns():
    """5.3b 输出经本块 ref 的 returns 目标赋值 → 通过。"""
    doc = {
        "block 导出": {
            "inputs": {"username": "str"},
            "outputs": "登录成功",
            "Sequence": [
                {
                    "ref": "登录/登录",
                    "args": {"username": "this/账号", "password": "this/密"},
                    "returns": {"login_success": "this/登录成功"},
                }
            ],
        },
        "block 登录": {
            "inputs": {"username": "str", "password": "str"},
            "outputs": "login_success",
            "Sequence": [{"Action": "提取 [[set:this/login_success]]"}],
        },
    }
    result = parse_doc("导出", doc, RESOLVER)
    assert not any(i.code == "ref.output_not_set" for i in result.checks.issues)


# ---- 5.4 可定位与验证条件 ----

def test_action_not_locatable_fails():
    """5.4 动作既无 CSS 也无自然语言描述 → locatable.not_locatable。"""
    result = parse_doc("坏", {"block 坏": {"Action": ""}}, RESOLVER)
    issues = [i for i in result.checks.issues if i.code == "locatable.not_locatable"]
    assert issues
    assert "无 CSS 提示" in issues[0].message


def test_action_with_css_passes():
    result = parse_doc(
        "好", {"block 好": {"Action": {"CSS": "button.ok"}}}, RESOLVER
    )
    assert not any(i.code == "locatable.not_locatable" for i in result.checks.issues)


def test_step_missing_expect_fails():
    """5.4 每步有验证条件：Step 缺 expect → verify.missing_condition。"""
    result = parse_doc("坏", {"block 坏": {"Step": {"action": "点"}}}, RESOLVER)
    assert any(i.code == "verify.missing_condition" for i in result.checks.issues)


def test_branch_missing_branches_fails():
    result = parse_doc("坏", {"block 坏": {"Branch": {"action": "点"}}}, RESOLVER)
    assert any(i.code == "verify.missing_condition" for i in result.checks.issues)


def test_loop_until_missing_until_fails():
    result = parse_doc("坏", {"block 坏": {"LoopUntil": {"action": "点", "max": 5}}}, RESOLVER)
    assert any(i.code == "verify.missing_condition" for i in result.checks.issues)


def test_step_missing_action_fails():
    """5.4 结构缺失：Step 缺 action → structure.missing_field。"""
    result = parse_doc("坏", {"block 坏": {"Step": {"expect": "出现"}}}, RESOLVER)
    assert any(i.code == "structure.missing_field" for i in result.checks.issues)


# ---- 5.5 条件谓词结构可校验 ----

def test_condition_empty_fails():
    """5.5 条件谓词缺描述 → predicate.empty_condition。"""
    result = parse_doc("坏", {"block 坏": {"Condition": ""}}, RESOLVER)
    assert any(i.code == "predicate.empty_condition" for i in result.checks.issues)


def test_condition_mapping_without_desc_fails():
    result = parse_doc("坏", {"block 坏": {"Condition": {"目标": "工作台"}}}, RESOLVER)
    assert any(i.code == "predicate.empty_condition" for i in result.checks.issues)


def test_condition_target_out_of_scope_fails():
    """5.5 谓词目标指向越作用域变量 → scope.out_of_scope。"""
    doc = {
        "block 坏": {
            "Condition": {"描述": "检查", "目标": "[[get:this/孙/深]]"}
        }
    }
    result = parse_doc("坏", doc, RESOLVER)
    assert any(i.code == "scope.out_of_scope" for i in result.checks.issues)


def test_condition_valid_passes():
    result = parse_doc("好", {"block 好": {"Condition": '出现"工作台"'}}, RESOLVER)
    assert not any(i.code.startswith("predicate") for i in result.checks.issues)


# ---- 5.6 CheckReport 汇总 ----

def test_report_failure_with_readable_issues():
    """5.6 失败文档：结论失败 + 逐条可读错误（code/message/rule/loc）。"""
    doc = {
        "block 坏": {
            "Sequence": [
                {"Flog": "x"},
                {"Step": {"action": "点"}},  # 缺 expect
            ]
        }
    }
    result = parse_doc("坏", doc, RESOLVER)
    report = result.checks
    assert report.ok is False
    assert report.issues
    for issue in report.issues:
        assert isinstance(issue, CheckIssue)
        assert issue.code and issue.message and issue.rule
    assert any(i.code == "structure.invalid_node" for i in report.issues)
    assert any(i.code == "verify.missing_condition" for i in report.issues)


def test_report_issues_sorted_and_deduped():
    """5.6 错误清单按位置/错误码排序且去重。"""
    doc = {"block 坏": {"Sequence": [{"Flog": "a"}, {"Flog": "b"}]}}
    result = parse_doc("坏", doc, RESOLVER)
    paths = [i.loc.path for i in result.checks.issues]
    assert paths == sorted(paths)


def test_report_passes_ok_empty():
    """5.6 通过文档：结论通过、错误清单为空。"""
    result = parse_doc("主流程", _MAIN_DOC, RESOLVER)
    assert result.checks.ok is True
    assert result.checks.issues == ()


# ---- 5.7 块内 get 变量已定义校验（scope.get_undeclared） ----

def test_get_undeclared_variable_fails():
    """get 读取的变量既非 inputs、也未在块内 set/ref returns 定义 → scope.get_undeclared。"""
    doc = {
        "block 坏": {
            "Sequence": [
                {"Step": {"action": "填 [[get:this/不存在的变量]]", "expect": "ok"}}
            ]
        }
    }
    result = parse_doc("坏", doc, RESOLVER)
    assert "scope.get_undeclared" in _codes(result)


def test_get_from_inputs_passes():
    """get 读取 inputs 声明的变量 → 通过。"""
    doc = {
        "block 好": {
            "inputs": {"username": "str"},
            "Sequence": [{"Step": {"action": "填 [[get:this/username]]", "expect": "ok"}}],
        }
    }
    result = parse_doc("好", doc, RESOLVER)
    assert "scope.get_undeclared" not in _codes(result)
    assert result.checks.ok is True


def test_get_from_block_set_passes():
    """get 读取块内 set 过的变量 → 通过。"""
    doc = {
        "block 好": {
            "Sequence": [
                {"Step": {"action": "提取 [[set:str:this/x]]", "expect": "ok"}},
                {"Step": {"action": "填 [[get:this/x]]", "expect": "ok"}},
            ]
        }
    }
    result = parse_doc("好", doc, RESOLVER)
    assert "scope.get_undeclared" not in _codes(result)


def test_get_from_ref_returns_passes():
    """get 读取 ref returns 目标变量（子块输出回收）→ 通过。"""
    doc = {
        "block 主": {
            "Sequence": [
                {"ref": "this/子块", "returns": {"result": "this/结果"}},
                {"Step": {"action": "填 [[get:this/结果]]", "expect": "ok"}},
            ]
        },
        "block 子块": {
            "outputs": "result",
            "Sequence": [{"Step": {"action": "提取 [[set:str:this/result]]", "expect": "ok"}}],
        },
    }
    result = parse_doc("主", doc, RESOLVER)
    assert "scope.get_undeclared" not in _codes(result)


def test_get_in_condition_validated():
    """Condition 里的 get 同样校验。"""
    doc = {
        "block 坏": {
            "Sequence": [{"Step": {"action": "点x", "expect": "出现 [[get:this/未定义]]"}}]
        }
    }
    result = parse_doc("坏", doc, RESOLVER)
    assert "scope.get_undeclared" in _codes(result)
