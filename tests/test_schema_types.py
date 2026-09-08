"""类型系统收敛测试：TypeSpec 注册表 + isinstance 校验 + coerce。"""
import pytest

from webops.schema.errors import SchemaTypeError
from webops.schema.models import PageRef
from webops.schema.types import (
    TYPE_REGISTRY,
    check_type,
    coerce,
    infer_type,
    validate_type_name,
)


def test_registry_has_english_tokens():
    assert set(TYPE_REGISTRY) == {"str", "int", "float", "bool", "page_ref"}


def test_py_types_mapped():
    assert TYPE_REGISTRY["str"].py_type is str
    assert TYPE_REGISTRY["int"].py_type is int
    assert TYPE_REGISTRY["float"].py_type is float
    assert TYPE_REGISTRY["bool"].py_type is bool
    assert TYPE_REGISTRY["page_ref"].py_type is PageRef


def test_validate_unknown_token_raises():
    with pytest.raises(SchemaTypeError):
        validate_type_name("文本")  # 中文名不再登记


@pytest.mark.parametrize(
    ("token", "good", "bad"),
    [
        ("str", "abc", 5),
        ("int", 5, "abc"),
        ("float", 1.5, "abc"),
        ("bool", True, 1),
    ],
)
def test_check_type_isinstance(token, good, bad):
    check_type(token, good)
    with pytest.raises(SchemaTypeError):
        check_type(token, bad)


def test_int_excludes_bool():
    with pytest.raises(SchemaTypeError):
        check_type("int", True)  # bool 是 int 子类，须排除


def test_page_ref_checked_by_isinstance():
    pr = PageRef(page_id="1")
    check_type("page_ref", pr)
    with pytest.raises(SchemaTypeError):
        check_type("page_ref", "http://x")  # 字符串不是页签引用


def test_coerce_basic():
    assert coerce("int", "123") == 123
    assert coerce("float", "1.5") == 1.5
    assert coerce("bool", "true") is True
    assert coerce("str", 123) == "123"


@pytest.mark.parametrize("raw", ["abc", "", "1.5x"])
def test_coerce_int_failure(raw):
    with pytest.raises(SchemaTypeError):
        coerce("int", raw)


def test_coerce_page_ref_rejected():
    with pytest.raises(SchemaTypeError):
        coerce("page_ref", "http://x")  # 页签引用不能由文本产生


def test_infer_type_english():
    assert infer_type(True) == "bool"
    assert infer_type(5) == "int"
    assert infer_type(1.5) == "float"
    assert infer_type(PageRef(page_id="1")) == "page_ref"
    assert infer_type("abc") == "str"
