import importlib.util
import json
from pathlib import Path

_path = Path(__file__).parent.parent / "tools" / "key_capture" / "capture_keys.py"
_spec = importlib.util.spec_from_file_location("capture_keys", _path)
ck = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ck)


def test_finds_nested_keys_with_parent_fields():
    data = {"data": {"productKey": "pk", "deviceName": "a1b2c3d4e5f6",
                     "accessInfo": {"accessKey": "AbCdEfGh10x1Y", "accessToken": "Zm9v="}}}
    assert list(ck.find_keys(data)) == [{"deviceName": "a1b2c3d4e5f6", "accessKey": "AbCdEfGh10x1Y",
                                         "accessToken": "Zm9v=", "productKey": "pk"}]


def test_finds_keys_in_lists_and_json_strings():
    inner = json.dumps({"deviceName": "b", "accessKey": "k2", "accessToken": "t2="})
    data = {"list": [{"deviceName": "a", "accessKey": "k1", "accessToken": "t1="}], "wrapped": inner}
    assert [k["deviceName"] for k in ck.find_keys(data)] == ["a", "b"]


def test_ignores_responses_without_keys():
    assert list(ck.find_keys({"deviceName": "a", "accessKey": "only-half"})) == []
