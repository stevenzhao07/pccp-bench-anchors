#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""emu_register.py —— 把我们的陈述改成 SCITT 模拟器能收的形状，再提交、再验。

为什么需要这一版：原始 out/statement_A0003.cose 被模拟器拒收，
错误是 urn:ietf:params:scitt:error:invalidInput / "Claim is not a valid COSE message"。
读它的校验代码（scitt.py:224-241）才看清真正原因——不是签名坏了，是**缺三个保护头**：

  Algorithm    (label 1)   我们的陈述有
  ContentType  (label 3)   我们没有  → 拒收
  CWTClaims    (label 14)  我们没有  → 拒收（且 iss/sub 两个 claim 必填）

这不是猜测：draft-gruszka 也记了同一个现象（emulator 要求 label 3 与 label 14）。
所以我们做两件不同的事：
  A 记下"原样被拒"这个**互操作缺陷**（对方实现与我们实现的分歧点）；
  B 补上头部后再提交，拿到回执，再独立验回执。

用法：
  python emu_register.py --statement out/statement_A0003.cose --key out/scitt_test_key.json \
      --iss urn:pccp-bench:test-key-20261127 --sub pccp-bench:v0.3.2 --out out/statement_A0003_scitt.cose
"""
from __future__ import annotations

import argparse
import cbor2
import cwt
import pycose
import pycose.headers
from pycose.keys.ec2 import EC2Key
from pycose.messages import Sign1Message

CWTClaims = 14


def load_payload(path: str) -> bytes:
    raw = open(path, "rb").read()
    obj = cbor2.loads(raw)
    val = obj.value if hasattr(obj, "tag") else obj
    return val[2]                      # COSE_Sign1 = [phdr, uhdr, payload, sig]


def build(payload: bytes, pem: bytes, iss: str, sub: str) -> bytes:
    key = cwt.COSEKey.from_pem(pem, kid=None)
    kid = getattr(key, "kid", None) or "8ddb6706b8fe0bfa"
    key_dict = key.to_dict()
    key_dict["kid"] = kid.encode("ascii") if isinstance(kid, str) else kid
    sign_key = EC2Key.from_dict(key_dict)

    cwt_token = cwt.encode({1: iss, 2: sub}, key)
    phdr = {
        pycose.headers.Algorithm: -7,     # ES256
        pycose.headers.KID: (kid.encode("ascii") if isinstance(kid, str) else kid),
        CWTClaims: cwt_token,
        pycose.headers.ContentType: "application/json",
    }
    msg = Sign1Message(phdr=phdr, uhdr={}, payload=payload)
    msg.key = sign_key
    raw = msg.encode(tag=True)
    # pycose 1.1 的 encode 出来，cbor2 读回时把 CBOR 数组解成 tuple，而它自己的
    # decode() 只接受 list（cosemessage.py:63 判断 isinstance(list)），于是自相矛盾。
    # 这里重排一次：tag 保留，数组归一成 list。
    obj = cbor2.loads(raw)
    body = obj.value if hasattr(obj, "tag") else obj
    body = [bytes(x) if isinstance(x, (bytes, bytearray))
            else (dict(x) if not isinstance(x, (list, tuple)) else list(x)) for x in body]
    return cbor2.dumps(cbor2.CBORTag(18, body))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--statement", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--iss", default="urn:pccp-bench:test-key-20261127")
    ap.add_argument("--sub", default="pccp-bench:v0.3.2")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    payload = load_payload(a.statement)
    pem = open(a.key, "rb").read()
    claim = build(payload, pem, a.iss, a.sub)
    open(a.out, "wb").write(claim)
    print("写出 %s（%d B）；payload %d B；头：alg=-7 / cty=application/json / cwt_claims{1:iss,2:sub}"
          % (a.out, len(claim), len(payload)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

