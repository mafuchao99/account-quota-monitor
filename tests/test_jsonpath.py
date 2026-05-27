from cpa_monitor.infrastructure.jsonpath import get_path


def test_get_path_supports_nested_values_and_indexes():
    payload = {"summary": {"total": 52}, "items": [{"name": "plus"}]}

    assert get_path(payload, "$.summary.total") == 52
    assert get_path(payload, "$.items[0].name") == "plus"


def test_get_path_returns_default_for_missing_values():
    assert get_path({"a": {}}, "$.a.b", default=0) == 0
