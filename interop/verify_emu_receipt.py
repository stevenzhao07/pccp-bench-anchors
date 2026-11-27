#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_emu_receipt.py —— 用**我们自己的代码路径**去验 SCITT 模拟器发的回执。

为什么再写一遍：对方有 verify-receipt，我们跑通了是"用它验它"。那是 T4。
这里按回执结构自己重算 leaf、自己重算 root、自己验 ECDSA、自己验证书链，
再和对方 verifier 的读数比对——两个代码库对同一份字节得出同一个结论，才叫互操作证据。

数学（CCF 树算法，见 emulator/ccf.py:151-186）：
  tbi   = CBOR(["CounterSignatureV2", phdr, sign_protected, b"", payload, [sig]])
  leaf  = SHA256(internal_hash || SHA256(internal_data) || SHA256(tbi))
  root  = 逐层 SHA256(left_hash||cur) 或 SHA256(cur||right_hash)
  校验  = node_cert 公钥对 root 做 ECDSA-SHA256（签名是 raw r||s，不是 DER）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys

import cbor2
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils


def sha256(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def load_claim(path):
    raw = open(path, "rb").read()
    obj = cbor2.loads(raw)
    body = obj.value if hasattr(obj, "tag") else obj
    return [cbor2.dumps(x) if not isinstance(x, bytes) else x for x in body]


def load_receipt(path):
    obj = cbor2.loads(open(path, "rb").read())
    body = obj.value if hasattr(obj, "tag") else obj
    sign_protected, contents = body[0], body[1]
    if not isinstance(sign_protected, bytes):
        sign_protected = cbor2.dumps(sign_protected)
    [signature, node_cert_der, proof, leaf_info] = contents
    return sign_protected, signature, node_cert_der, proof, leaf_info


def p1363_to_der(sig: bytes) -> bytes:
    n = len(sig) // 2
    r, s = int.from_bytes(sig[:n], "big"), int.from_bytes(sig[n:], "big")
    return utils.encode_dss_signature(r, s)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--claim", required=True)
    ap.add_argument("--receipt", required=True)
    ap.add_argument("--service-parameters", required=True)
    a = ap.parse_args()

    phdr, _uhdr, payload, sig = load_claim(a.claim)
    sign_protected, signature, node_cert_der, proof, leaf_info = load_receipt(a.receipt)
    internal_hash, internal_data = leaf_info
    if not isinstance(internal_data, bytes):
        internal_data = str(internal_data).encode("ascii")

    tbi = cbor2.dumps(["CounterSignatureV2", phdr, sign_protected, b"", payload, [sig]])
    leaf = sha256(internal_hash + sha256(internal_data) + sha256(tbi))

    cur = leaf
    for step in proof:
        left, h = step[0], step[1]
        cur = sha256(h + cur) if left else sha256(cur + h)
    root = cur

    node_cert = x509.load_der_x509_certificate(node_cert_der)
    node_cert.public_key().verify(p1363_to_der(signature), root,
                                 ec.ECDSA(utils.Prehashed(hashes.SHA256())))

    params = json.load(open(a.service_parameters, encoding="utf-8"))
    service_cert = x509.load_pem_x509_certificate(params["serviceCertificate"].encode())
    assert node_cert.issuer == service_cert.subject, "node cert 非该服务签发"
    service_cert.public_key().verify(node_cert.signature, node_cert.tbs_certificate_bytes,
                                     ec.ECDSA(node_cert.signature_hash_algorithm))

    ok = {
        "leaf": leaf.hex(),
        "root": root.hex(),
        "entry_id": internal_data.decode("ascii", "replace"),
        "service_id": params.get("serviceId"),
        "tree_alg": params.get("treeAlgorithm"),
        "signature": "ECDSA-P256-SHA256 over root: OK",
        "cert_chain": "node <- service: OK",
    }
    for k, v in ok.items():
        print("%-12s %s" % (k, v))
    print("EMU_RECEIPT_VERIFIED_BY_OUR_CODE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
