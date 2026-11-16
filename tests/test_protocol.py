import json, socket, threading, base64
from custom_components.cloud_intelligence_plugs import alcs as a
TOK="Zm9vYmFyYmF6cXV4ZXhhbXBsZT0="
def mock_plug():
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.bind(("127.0.0.1",5683)); st={"p":1}; ses={}
    def run():
        while True:
            data,addr=s.recvfrom(4096); m=a.coap_parse(data)
            if m["code"]==0: continue
            if b"core/service/auth" not in data and b"auth" not in data[:200]:
                pass
            if not ses or b"auth" in data:
                p=json.loads(m["payload"])["params"]
                assert p["sign"]==base64.b64encode(a._hmac_sha1(TOK,p["randomKey"])).decode()
                dr="DevRandom12345a"; ses["k"]=a._hmac_sha1(TOK,p["randomKey"]+dr)[:16]
                body=json.dumps({"id":"1","code":200,"data":{"randomKey":dr,"sessionId":65940,"opt":1,"seqStart":0}}).encode()
                s.sendto(a.coap_build(2,0,m["mid"],b"",[]),addr); s.sendto(a.coap_build(2,0x45,m["mid"],m["token"],[],body),addr); continue
            req=json.loads(a.decrypt(ses["k"],m["payload"]))
            if req["method"].endswith("set"): st["p"]=req["params"]["powerstate"]; d={}
            else: d={"powerstate":st["p"]}
            out=a.encrypt(ses["k"],json.dumps({"id":req["id"],"code":200,"data":d}).encode())
            s.sendto(a.coap_build(2,0,m["mid"],b"",[]),addr); s.sendto(a.coap_build(0,0x45,7,m["token"],[],out),addr)
    threading.Thread(target=run,daemon=True).start()
def test_roundtrip():
    mock_plug()
    p=a.AlcsPlug("127.0.0.1","a1JG8An8ORa","a1b2c3d4e5f6","AbCdEfGh10x1Y",TOK)
    assert p.test() is True
    p.set_power(False); assert p.get_power() is False
    p.set_power(True); assert p.get_power() is True
    p.close()
