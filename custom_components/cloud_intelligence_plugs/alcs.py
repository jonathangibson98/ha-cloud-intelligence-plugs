"""Local client for Cloud Intelligence (Alibaba IoT Living) plugs.

Speaks Alibaba's local protocol (ALCS): CoAP over UDP 5683, an HMAC login
using the per-device accessKey/accessToken, then AES-128-CBC payloads.
Blocking code — Home Assistant runs it in the executor.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import random
import socket
import string
import struct
import threading
import time

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

PORT = 5683
MCAST = "224.0.1.187"
IV = b"a1b1c1d1e1f1g1h1"
OPT_URI_PATH, OPT_CONTENT_FORMAT, OPT_SESSIONID = 11, 12, 71
GET = 0x01
CON, NON, ACK = 0, 1, 2


class AlcsError(Exception):
    """Base error."""


class AlcsAuthError(AlcsError):
    """The plug rejected the access key/token."""


class AlcsTimeout(AlcsError):
    """The plug did not answer."""


# ---------------- CoAP framing ----------------
def _uint(v: int) -> bytes:
    out = b""
    while v:
        out = bytes([v & 0xFF]) + out
        v >>= 8
    return out


def _ext(n: int) -> tuple[int, bytes]:
    if n < 13:
        return n, b""
    if n < 269:
        return 13, bytes([n - 13])
    return 14, struct.pack("!H", n - 269)


def coap_build(mtype, code, mid, token, options, payload=b"") -> bytes:
    out = bytearray([0x40 | (mtype << 4) | len(token), code]) + struct.pack("!H", mid) + token
    last = 0
    for num, val in sorted(options, key=lambda o: o[0]):
        d, dext = _ext(num - last)
        ln, lext = _ext(len(val))
        out += bytes([(d << 4) | ln]) + dext + lext + val
        last = num
    if payload:
        out += b"\xff" + payload
    return bytes(out)


def coap_parse(data: bytes) -> dict | None:
    if len(data) < 4:
        return None
    b0, code, mid = data[0], data[1], struct.unpack("!H", data[2:4])[0]
    tkl = b0 & 0x0F
    msg = {"type": (b0 >> 4) & 3, "code": code, "mid": mid,
           "token": data[4:4 + tkl], "payload": b""}
    i = 4 + tkl
    while i < len(data):
        if data[i] == 0xFF:
            msg["payload"] = data[i + 1:]
            break
        d, ln = data[i] >> 4, data[i] & 0x0F
        i += 1
        if d == 13:
            i += 1
        elif d == 14:
            i += 2
        if ln == 13:
            ln = data[i] + 13
            i += 1
        elif ln == 14:
            ln = struct.unpack("!H", data[i:i + 2])[0] + 269
            i += 2
        i += ln
    return msg


def _path_opts(path: str) -> list[tuple[int, bytes]]:
    return [(OPT_URI_PATH, p.encode()) for p in path.strip("/").split("/") if p]


# ---------------- crypto ----------------
def _hmac_sha1(key: str, msg: str) -> bytes:
    return hmac.new(key.encode(), msg.encode(), hashlib.sha1).digest()


def _cbc(key: bytes, data: bytes, enc: bool) -> bytes:
    c = Cipher(algorithms.AES(key), modes.CBC(IV))
    ctx = c.encryptor() if enc else c.decryptor()
    return ctx.update(data) + ctx.finalize()


def encrypt(key: bytes, data: bytes) -> bytes:
    # Alibaba quirk: the padded final block is its own CBC run from the fixed IV.
    full = len(data) & ~15
    pad = 16 - (len(data) - full)
    head = _cbc(key, data[:full], True) if full else b""
    return head + _cbc(key, data[full:] + bytes([pad]) * pad, True)


def decrypt(key: bytes, data: bytes) -> bytes:
    if not data or len(data) % 16:
        raise AlcsError("bad ciphertext length")
    last = _cbc(key, data[-16:], False)
    pad = last[-1]
    if not 1 <= pad <= 16:
        raise AlcsError("bad padding")
    head = _cbc(key, data[:-16], False) if len(data) > 16 else b""
    return head + last[:-pad]


# ---------------- client ----------------
class AlcsPlug:
    """One plug. Thread-safe; keeps its login session and re-logs in on failure."""

    def __init__(self, host, product_key, device_name, access_key, access_token):
        self.host = host
        self.pk = product_key
        self.dn = device_name
        self.access_key = access_key
        self.access_token = access_token
        self._lock = threading.Lock()
        self._sock: socket.socket | None = None
        self._mid = random.randint(1, 60000)
        self._seq = random.randint(1, 1000)
        self._session_id: int | None = None
        self._key: bytes | None = None
        self._authed_at = 0.0

    # -- transport --
    def _socket(self) -> socket.socket:
        if self._sock is None:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.settimeout(2)
        return self._sock

    def close(self) -> None:
        with self._lock:
            self._reset()

    def _reset(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        self._sock = None
        self._key = None
        self._session_id = None

    def _request(self, path, payload, options=()) -> dict:
        sock = self._socket()
        self._mid = (self._mid + 1) & 0xFFFF
        token = os.urandom(4)
        pkt = coap_build(CON, GET, self._mid, token, _path_opts(path) + list(options), payload)
        for _ in range(3):
            sock.sendto(pkt, (self.host, PORT))
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                try:
                    data, addr = sock.recvfrom(4096)
                except socket.timeout:
                    break
                except OSError as err:
                    raise AlcsTimeout(str(err)) from err
                m = coap_parse(data)
                if not m:
                    continue
                if m["type"] == CON:
                    sock.sendto(coap_build(ACK, 0, m["mid"], b"", []), addr)
                if m["code"] == 0:
                    deadline = time.monotonic() + 4
                    continue
                if m["token"] == token:
                    return m
        raise AlcsTimeout(f"No reply from {self.host}")

    @staticmethod
    def _code_ok(m) -> bool:
        return (m["code"] >> 5) == 2

    # -- protocol --
    def _auth(self) -> None:
        client_rand = "".join(random.choice(string.ascii_letters + string.digits) for _ in range(16))
        sign = base64.b64encode(_hmac_sha1(self.access_token, client_rand)).decode()
        self._seq += 1
        body = json.dumps({
            "version": "1.0", "method": "core/service/auth", "id": self._seq,
            "params": {"prodKey": self.pk, "deviceName": self.dn, "encrypt": "payload",
                       "randomKey": client_rand, "sign": sign, "accessKey": self.access_key},
        }, separators=(",", ":")).encode()
        m = self._request(f"/dev/{self.pk}/{self.dn}/core/service/auth", body,
                          [(OPT_CONTENT_FORMAT, _uint(50))])
        if not self._code_ok(m):
            raise AlcsAuthError(f"auth CoAP code {m['code'] >> 5}.{m['code'] & 31:02d}")
        try:
            resp = json.loads(m["payload"].decode())
        except ValueError as err:
            raise AlcsError("unreadable auth reply") from err
        if int(resp.get("code", 0)) != 200:
            raise AlcsAuthError(f"auth refused: {resp.get('code')}")
        data = resp["data"]
        self._session_id = int(data["sessionId"])
        self._key = _hmac_sha1(self.access_token, client_rand + data["randomKey"])[:16]
        self._authed_at = time.monotonic()

    def _secure(self, method_path, method, params) -> dict:
        # Device sessions last 24h; re-login well before that.
        if self._key is None or time.monotonic() - self._authed_at > 3600:
            self._auth()
        self._seq += 1
        body = json.dumps({"id": str(self._seq), "version": "1.0", "params": params,
                           "method": method}, separators=(",", ":")).encode()
        opts = [(OPT_CONTENT_FORMAT, _uint(42)),
                (OPT_SESSIONID, self._session_id.to_bytes(4, "big"))]
        m = self._request(f"/sys/{self.pk}/{self.dn}/{method_path}", encrypt(self._key, body), opts)
        if not self._code_ok(m):
            raise AlcsError(f"{method} CoAP code {m['code'] >> 5}.{m['code'] & 31:02d}")
        if not m["payload"]:
            return {}
        try:
            resp = json.loads(decrypt(self._key, m["payload"]).decode())
        except ValueError as err:
            raise AlcsError("unreadable reply") from err
        if int(resp.get("code", 200)) != 200:
            raise AlcsError(f"{method} refused: {resp.get('code')}")
        return resp

    def _call(self, method_path, method, params) -> dict:
        with self._lock:
            try:
                return self._secure(method_path, method, params)
            except (AlcsAuthError, AlcsTimeout):
                self._reset()
                raise
            except AlcsError:
                # Session may have expired or the plug rebooted: log in fresh once.
                self._reset()
                return self._secure(method_path, method, params)

    def test(self) -> bool:
        with self._lock:
            self._reset()
            self._auth()
        return self.get_power()

    def get_power(self) -> bool:
        resp = self._call("thing/service/property/get", "thing.service.property.get", ["powerstate"])
        val = (resp.get("data") or {}).get("powerstate")
        if val is None:
            raise AlcsError("plug did not report powerstate")
        return bool(int(val))

    def set_power(self, on: bool) -> None:
        self._call("thing/service/property/set", "thing.service.property.set",
                   {"powerstate": 1 if on else 0})


def discover(timeout: float = 3.0) -> dict[str, str]:
    """Return {deviceName: ip} for every ALCS device that answers on the LAN."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.settimeout(0.5)
    body = json.dumps({"id": "1", "version": "1.0", "params": {},
                       "method": "core.service.dev"}).encode()
    pkt = coap_build(NON, GET, random.randint(1, 60000), os.urandom(4),
                     _path_opts("/dev/core/service/dev"), body)
    found: dict[str, str] = {}
    try:
        for target in (MCAST, "255.255.255.255"):
            try:
                s.sendto(pkt, (target, PORT))
            except OSError:
                pass
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                data, addr = s.recvfrom(4096)
            except socket.timeout:
                continue
            m = coap_parse(data)
            if not m or not m["payload"]:
                continue
            try:
                payload = json.loads(m["payload"].decode())
            except ValueError:
                continue
            data_ = payload.get("data") or {}
            devs = data_.get("devices", data_) if isinstance(data_, dict) else data_
            if isinstance(devs, dict):
                devs = [devs]
            for dev in devs if isinstance(devs, list) else []:
                if not isinstance(dev, dict):
                    continue
                for prof in dev.get("profile") or [dev]:
                    if isinstance(prof, dict) and prof.get("deviceName"):
                        found[prof["deviceName"]] = dev.get("addr") or addr[0]
    finally:
        s.close()
    return found
