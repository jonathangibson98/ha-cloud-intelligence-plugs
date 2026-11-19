"""mitmproxy add-on that prints Cloud Intelligence plug keys from the app's traffic.

Run it with run.sh (next to this file). It reads only responses that contain an
``accessToken`` and prints the four values the Home Assistant setup form asks for.
It doesn't save anything to disk.
"""
from __future__ import annotations

import json
from typing import Any, Iterator

LABELS = (
    ("deviceName", "Device name "),
    ("accessKey", "Access key  "),
    ("accessToken", "Access token"),
    ("productKey", "Product key "),
)


def _maybe_json(value: Any) -> Any:
    """Some APIs wrap JSON inside a string field. Unwrap it if so."""
    if isinstance(value, str) and "accessToken" in value:
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def find_keys(obj: Any, context: dict[str, Any] | None = None) -> Iterator[dict[str, str]]:
    """Yield every dict holding an accessKey and accessToken.

    deviceName and productKey are taken from the same dict, or from the nearest
    parent dict if the API keeps them one level up.
    """
    obj = _maybe_json(obj)
    if isinstance(obj, dict):
        here = {**(context or {}), **{k: v for k, v in obj.items() if k in ("deviceName", "productKey") and isinstance(v, str)}}
        if isinstance(obj.get("accessKey"), str) and isinstance(obj.get("accessToken"), str):
            yield {
                "deviceName": here.get("deviceName", ""),
                "accessKey": obj["accessKey"],
                "accessToken": obj["accessToken"],
                "productKey": here.get("productKey", ""),
            }
        for value in obj.values():
            yield from find_keys(value, here)
    elif isinstance(obj, list):
        for value in obj:
            yield from find_keys(value, context)


def format_entry(keys: dict[str, str]) -> str:
    lines = ["", "=" * 60, " Found plug keys - copy these into Home Assistant", "-" * 60]
    for field, label in LABELS:
        lines.append(f" {label} : {keys.get(field) or '(not in this response)'}")
    lines.append("=" * 60)
    return "\n".join(lines)


class KeyCapture:
    def __init__(self) -> None:
        self.seen: set[tuple[str, str, str]] = set()

    def running(self) -> None:
        print("\nKey capture is running. Open Cloud Intelligence on your phone and tap into each plug.", flush=True)
        print("Press Ctrl+C here when you're done.\n", flush=True)

    def response(self, flow: Any) -> None:
        response = getattr(flow, "response", None)
        if response is None:
            return
        try:
            text = response.get_text(strict=False)
        except Exception:  # binary or undecodable body
            return
        if not text or "accessToken" not in text:
            return
        try:
            data = json.loads(text)
        except ValueError:
            return
        for keys in find_keys(data):
            ident = (keys["deviceName"], keys["accessKey"], keys["accessToken"])
            if ident in self.seen:
                continue
            self.seen.add(ident)
            print(format_entry(keys), flush=True)


addons = [KeyCapture()]
