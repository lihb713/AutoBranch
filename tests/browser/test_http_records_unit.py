"""HttpRecorder 纯逻辑：清单/批量读取/请求头记录（无浏览器）。"""

from __future__ import annotations

from autobranch.browser import HttpRecorder


class _Req:
    def __init__(self, method: str, headers: dict[str, str]) -> None:
        self.method = method
        self.headers = headers


class _Resp:
    def __init__(self, method: str, url: str, body: bytes, req_headers: dict[str, str]) -> None:
        self.request = _Req(method, req_headers)
        self.url = url
        self.status = 200
        self.headers = {"content-type": "application/json"}

    def body(self) -> bytes:
        return self._body


def test_list_and_get_all_records_with_request_headers():
    rec = HttpRecorder()
    resp = _Resp("GET", "https://x/api/a", b"{}", {"Cookie": "sid=1"})
    resp._body = b"{}"
    rec.record_response(resp)
    assert rec.list_records() == [("GET", "https://x/api/a", 200)]
    records = rec.get_all_records()
    assert len(records) == 1
    assert records[0].body == "{}"
    assert records[0].request_headers["Cookie"] == "sid=1"
    rec.clear()
    assert rec.list_records() == []
