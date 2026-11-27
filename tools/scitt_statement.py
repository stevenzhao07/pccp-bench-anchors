#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scitt_statement.py —— 把锚定事实写成 SCITT 风格的 Signed Statement（COSE_Sign1）。

为什么要这件东西：我们现有的回执是自己的 JSON + Rekor hashedrekord，
只有我们那 6 个脚本能验。SCITT（IETF）定义的是另一种更通用的形状：
  Signed Statement（COSE_Sign1 承载） → Transparency Service → Receipt
形状对上之后，外人可以用通用 COSE 工具验，不必装我们的东西。

诚实标注：
  * 本文件签的是**一次性测试密钥**（P-256，生成后写在 out/scitt_test_key.json），
    不是 Fulcio 身份、不是 GitHub OIDC 身份。它证明的是"格式能对上、签名能验、
    改一个字节就验不过"，不证明"这是我们这个组织发的"。
  * 正式身份绑定仍要走 OIDC（A-0001/A-0002/A-0003 那条路）。
  * 签名用 cryptography 库（便利），验签侧用零依赖实现（verify_scitt_statement.py）。
"""
import argparse
import base64
import hashlib
import json
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils

HERE = os.path.dirname(os.path.abspath(__file__))


# ---------- 最小 CBOR 编码器（只做本文件需要的形状） ----------
def cbor(obj) -> bytes:
    if isinstance(obj, bool):
        return b"\xf5" if obj else b"\xf4"
    if isinstance(obj, int):
        if obj >= 0:
            if obj < 24:
                return bytes([0x00 + obj])
            if obj < 256:
                return bytes([0x18, obj])
            if obj < 65536:
                return bytes([0x19]) + obj.to_bytes(2, "big")
            return bytes([0x1A]) + obj.to_bytes(4, "big")
        n = -1 - obj
        if n < 24:
            return bytes([0x20 + n])
        if n < 256:
            return bytes([0x38, n])
        return bytes([0x39]) + n.to_bytes(2, "big")
    if isinstance(obj, bytes):
        return _head(0x40, len(obj)) + obj
    if isinstance(obj, str):
        raw = obj.encode("utf-8")
        return _head(0x60, len(raw)) + raw
    if isinstance(obj, (list, tuple)):
        return _head(0x80, len(obj)) + b"".join(cbor(x) for x in obj)
    if isinstance(obj, dict):
        out = _head(0xA0, len(obj))
        for k, v in obj.items():
            out += cbor(k) + cbor(v)
        return out
    raise TypeError("unsupported cbor type: %r" % type(obj))


def _head(base, n):
    if n < 24:
        return bytes([base + n])
    if n < 256:
        return bytes([base + 0x18, n])
    if n < 65536:
        return bytes([base + 0x19]) + n.to_bytes(2, "big")
    return bytes([base + 0x1A]) + n.to_bytes(4, "big")


# ---------- 密钥 ----------
def load_or_make_key(path):
    if os.path.exists(path):
        with open(path, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=None)
    key = ec.generate_private_key(ec.SECP256R1())
    open(path, "wb").write(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    return key


def spki_der(pub):
    return pub.public_bytes(serialization.Encoding.DER,
                            serialization.PublicFormat.SubjectPublicKeyInfo)


def sign_es256(priv, msg: bytes) -> bytes:
    der = priv.sign(msg, ec.ECDSA(hashes.SHA256()))
    r, s = utils.decode_dss_signature(der)
    return r.to_bytes(32, "big") + s.to_bytes(32, "big")   # COSE 要 raw r||s


def build_statement(anchors, issuer, key_path):
    priv = load_or_make_key(key_path)
    kid = hashlib.sha256(spki_der(priv.public_key())).hexdigest()[:16]

    payload_doc = {
        "issuer": issuer,
        "statement_type": "pccp-bench-anchor",
        "created": "2026-11-27",
        "anchors": anchors,
        "note": "测试密钥签名；身份绑定未完成，正式版须走 OIDC",
    }
    payload = cbor(payload_doc)
    protected = cbor({1: -7})            # alg = ES256
    unprotected = {4: kid.encode()}      # kid
    sig_structure = cbor(["Signature1", protected, b"", payload])
    sig = sign_es256(priv, sig_structure)
    cose = cbor([protected, unprotected, payload, sig])
    return cose, kid, payload_doc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", required=True)
    ap.add_argument("--log-index", required=True)
    ap.add_argument("--uuid", required=True)
    ap.add_argument("--issuer", default="urn:pccp-bench:test-key-20261127")
    ap.add_argument("--key", default=os.path.join(HERE, "out", "scitt_test_key.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "out", "statement_A0003.cose"))
    a = ap.parse_args()

    digest = hashlib.sha256(open(a.artifact, "rb").read()).hexdigest()
    anchors = [{"subject_sha256": digest, "rekor_logIndex": int(a.log_index),
                "rekor_uuid": a.uuid, "artifact_bytes": os.path.getsize(a.artifact)}]
    cose, kid, doc = build_statement(anchors, a.issuer, a.key)
    open(a.out, "wb").write(cose)
    print(json.dumps({"out": a.out, "bytes": len(cose), "kid": kid,
                      "subject_sha256": digest, "cose_b64url": base64.urlsafe_b64encode(cose).decode()},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
