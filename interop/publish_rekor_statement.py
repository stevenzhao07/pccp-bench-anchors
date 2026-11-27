#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""publish_rekor_statement.py —— 把我们的 COSE 陈述写进**公共** Rekor（RFC 9162 日志）。

此举的性质：对外发布。已得用户明确批准（"发"）。
写入方式：hashedrekord —— 用我们的测试密钥对陈述 payload 的 sha256 做 ECDSA 签名，
Rekor 受理后返回 SET + 包含性证明 + integratedTime + logIndex。

为什么用 hashedrekord 而不是别的：
  Rekor 原生吃的是"某个摘要 + 某个签名 + 某把公钥"，我们的 payload 摘要与签名正好是这三样；
  这样拿到的回执与 CCF 模拟器那份是**两种不同的回执形状**，正是 A4 要的两服务对照。

用法：
  python publish_rekor_statement.py --statement out/statement_A0003_scitt.cose \
      --key out/scitt_test_key.json --out out/rekor_statement_entry.json
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys

import cbor2
import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

REKOR = "https://rekor.sigstore.dev"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--statement", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    raw = open(a.statement, "rb").read()
    body = cbor2.loads(raw)
    body = body.value if hasattr(body, "tag") else body
    payload = body[2]
    digest = hashlib.sha256(payload).hexdigest()

    key = serialization.load_pem_private_key(open(a.key, "rb").read(), None)
    pub_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    sig = key.sign(payload, ec.ECDSA(hashes.SHA256()))     # DER

    entry = {
        "apiVersion": "0.0.1",
        "kind": "hashedrekord",
        "spec": {
            "data": {"hash": {"algorithm": "sha256", "value": digest}},
            "signature": {
                "content": base64.b64encode(sig).decode(),
                "publicKey": {"content": base64.b64encode(pub_pem).decode()},
            },
        },
    }
    r = httpx.post(REKOR + "/api/v1/log/entries", json=entry, timeout=30)
    print("POST /api/v1/log/entries ->", r.status_code)
    if r.status_code != 201:
        print(r.text[:400])
        return 1

    data = r.json()
    uuid, obj = next(iter(data.items()))
    body_b64 = obj["body"]
    decoded = json.loads(base64.b64decode(body_b64))
    print("uuid        ", uuid)
    print("logIndex    ", obj.get("logIndex"))
    print("integratedTime", obj.get("integratedTime"))
    print("logID       ", obj.get("logID"))
    print("entry kind  ", decoded.get("kind"))
    print("digest in log", decoded["spec"]["data"]["hash"]["value"])

    out = {"uuid": uuid, "response": data, "statement_payload_sha256": digest,
           "publish_note": "已获用户明确批准（'发'）；本条目为 COSE 陈述的 payload 摘要+签名，hashedrekord 形状"}
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("写出", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
