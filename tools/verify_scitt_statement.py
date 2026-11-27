#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_scitt_statement.py —— 零依赖验 COSE_Sign1 签名的 Signed Statement。

只用标准库：自带最小 CBOR 解码器；P-256 验签复用 verify_zero_dep.py 的曲线实现。
因此别人不必装 cryptography / cosign / sigstore 也能验这一份。
"""
import argparse
import base64
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from verify_zero_dep import ecdsa_verify, CURVES  # noqa: E402


# ---------- 最小 CBOR 解码器 ----------
def cbor_decode(b, i=0):
    t = b[i]
    i += 1
    major, info = t >> 5, t & 0x1F
    if major == 0:
        return _val(b, info, i, 0)[0], _val(b, info, i, 0)[1]
    if major == 1:
        v, j = _val(b, info, i, 0)
        return -1 - v, j
    if major in (2, 3):
        n, j = _val(b, info, i, 0)
        raw = b[j:j + n]
        return (raw if major == 2 else raw.decode("utf-8")), j + n
    if major == 4:
        n, j = _val(b, info, i, 0)
        out = []
        for _ in range(n):
            v, j = cbor_decode(b, j)
            out.append(v)
        return out, j
    if major == 5:
        n, j = _val(b, info, i, 0)
        out = {}
        for _ in range(n):
            k, j = cbor_decode(b, j)
            v, j = cbor_decode(b, j)
            out[k] = v
        return out, j
    if major == 6:
        # 带标签（最典型是 COSE_Sign1 的 tag 18 = 0xD2）。RFC 9052 允许也鼓励带标签；
        # 早先这里直接抛 ValueError，等于"只认无标签的编码"，与规范相反 —— 已修。
        _tag, j = _val(b, info, i, 0)
        return cbor_decode(b, j)
    if major == 7 and info == 20:
        return False, i
    if major == 7 and info == 21:
        return True, i
    raise ValueError("unsupported cbor major %d info %d at %d" % (major, info, i - 1))


def _val(b, info, i, _unused):
    if info < 24:
        return info, i
    if info == 24:
        return b[i], i + 1
    if info == 25:
        return int.from_bytes(b[i:i + 2], "big"), i + 2
    if info == 26:
        return int.from_bytes(b[i:i + 4], "big"), i + 4
    raise ValueError("unsupported length info %d" % info)


def cbor(obj) -> bytes:      # 只用于重建 Sig_structure（与生成侧同形）
    if isinstance(obj, bool):
        return b"\xf5" if obj else b"\xf4"
    if isinstance(obj, int):
        if obj >= 0:
            return bytes([obj]) if obj < 24 else bytes([0x18, obj]) if obj < 256 else bytes([0x19]) + obj.to_bytes(2, "big")
        n = -1 - obj
        return bytes([0x20 + n]) if n < 24 else bytes([0x38, n])
    if isinstance(obj, bytes):
        return _h(0x40, len(obj)) + obj
    if isinstance(obj, str):
        r = obj.encode()
        return _h(0x60, len(r)) + r
    if isinstance(obj, (list, tuple)):
        return _h(0x80, len(obj)) + b"".join(cbor(x) for x in obj)
    if isinstance(obj, dict):
        return _h(0xA0, len(obj)) + b"".join(cbor(k) + cbor(v) for k, v in obj.items())
    raise TypeError(type(obj))


def _h(base, n):
    if n < 24:
        return bytes([base + n])
    if n < 256:
        return bytes([base + 0x18, n])
    return bytes([base + 0x19]) + n.to_bytes(2, "big")


def point_from_spki(der):
    """从 SubjectPublicKeyInfo 取 P-256 点。仅支持 EC + prime256v1。"""
    from verify_zero_dep import point_from_spki as f
    return f(der)


def _der_from_rs(r: int, s: int) -> bytes:
    """COSE 的 raw(r||s) 转 DER，好让零依赖验算器按同一口径解析。"""
    def enc(v):
        b = v.to_bytes(32, "big").lstrip(b"\x00") or b"\x00"
        if b[0] & 0x80:
            b = b"\x00" + b
        return b"\x02" + bytes([len(b)]) + b
    body = enc(r) + enc(s)
    return b"\x30" + bytes([len(body)]) + body


def verify(cose_bytes, spki_der):
    tagged18 = cose_bytes[:1] == b"\xd2"      # tag 18：COSE_Sign1 的标准编码
    cose, end = cbor_decode(cose_bytes, 0)
    if not isinstance(cose, list) or len(cose) != 4:
        return {"ok": False, "reason": "not a COSE_Sign1 4-element array"}
    protected, unprotected, payload, sig = cose
    hdr, _ = cbor_decode(protected, 0)
    alg = hdr.get(1) if isinstance(hdr, dict) else None
    if alg != -7:
        return {"ok": False, "reason": "alg is not ES256 (-7): %r" % (alg,)}
    sig_structure = cbor(["Signature1", protected, b"", payload])
    pub = point_from_spki(spki_der)
    if len(sig) != 64:
        return {"ok": False, "reason": "ES256 signature must be 64 bytes, got %d" % len(sig)}
    r = int.from_bytes(sig[:32], "big")
    s = int.from_bytes(sig[32:], "big")
    der = _der_from_rs(r, s)      # 复用零依赖验算器里的 DER 解析口径
    ok = ecdsa_verify(pub, sig_structure, der, curve="p256", hashname="sha256")
    doc = None
    try:
        doc, _ = cbor_decode(payload, 0)
    except Exception as exc:            # 载荷被改坏时不崩，如实报 FAIL
        return {"ok": False, "alg": alg, "payload_error": str(exc), "tagged18": tagged18,
                "kid": (unprotected or {}).get(4), "cose_len": len(cose_bytes)}
    return {"ok": ok, "alg": alg, "payload": doc, "tagged18": tagged18,
            "kid": (unprotected or {}).get(4), "cose_len": len(cose_bytes)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--statement", required=True, help=".cose 文件")
    ap.add_argument("--pubkey-pem", required=True, help="签名者公钥 PEM")
    ap.add_argument("--artifact", help="若给出，核对 statement 里的 subject_sha256")
    ap.add_argument("--tamper", action="store_true", help="翻转 payload 一个字节，应验不过")
    a = ap.parse_args()

    raw = open(a.statement, "rb").read()
    if a.tamper:
        # 翻签名最后一个字节：结构仍合法，只有签名该失效 → 用来证明它不是"永远 OK"
        raw = raw[:-1] + bytes([raw[-1] ^ 0x01])

    # 原先用 cryptography 解析 PEM，与"零依赖"的说法相矛盾；改用自带 PEM→DER，真的不再需要三方包。
    from verify_zero_dep import pem_to_der
    spki = pem_to_der(open(a.pubkey_pem, encoding="utf-8").read())

    res = verify(raw, spki)
    print("SCITT_STATEMENT")
    print("  ENCODING       %s" % ("tag 18 (COSE_Sign1)" if res.get("tagged18") else "untagged array"))
    print("  SIGNATURE      %s" % ("OK" if res["ok"] else "FAIL"))
    print("  ALG            %s" % res.get("alg"))
    print("  KID            %s" % (res.get("kid") or b"").decode(errors="replace"))
    doc = res.get("payload") or {}
    print("  ISSUER         %s" % doc.get("issuer"))
    subj = (doc.get("anchors") or [{}])[0].get("subject_sha256") if isinstance(doc.get("payload", doc), dict) else None
    if isinstance(doc, dict):
        subj = (doc.get("anchors") or [{}])[0].get("subject_sha256")
    print("  SUBJECT_SHA256 %s" % subj)
    if a.artifact and subj:
        got = hashlib.sha256(open(a.artifact, "rb").read()).hexdigest()
        print("  BINDING        %s" % ("OK" if got == subj else "FAIL (%s != %s)" % (got, subj)))
        res["ok"] = res["ok"] and got == subj
    print("SCITT_%s" % ("ALL_PASS" if res["ok"] else "HAS_FAIL"))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
