#!/usr/bin/env python3
"""verify_anchor.py — 把"锚定"验成三件事，全部纯标准库（无 sigstore SDK、无 openssl）。

三条独立判据：
  1 包含性（inclusion）：leaf → Merkle path → root，与条目自带 rootHash 一致
  2 checkpoint 签名：Rekor 公钥（P-256）对 checkpoint 文本做 ECDSA/SHA-256 验签
  3 绑定（binding）：条目 body 里的 payloadHash 与回执的 receipt_self_sha256 是否同值

用法：
  python verify_anchor.py --entry entry.json --public-key pub.pem [--receipt receipt.json]

边界（未实现，勿称已通过）：
  - SET（signedEntryTimestamp）签名
  - logID ↔ 公钥的对应关系登记校验（本工具只验"这把公钥签了这条 checkpoint"）
"""
import argparse
import base64
import hashlib
import json
import sys

# P-256
P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
A = P - 3
B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
GX = 0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296
GY = 0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5
G = (GX, GY)


def add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2 and (y1 + y2) % P == 0:
        return None
    if p1 == p2:
        lam = (3 * x1 * x1 + A) * pow(2 * y1, -1, P) % P
    else:
        lam = (y2 - y1) * pow(x2 - x1, -1, P) % P
    x3 = (lam * lam - x1 - x2) % P
    y3 = (lam * (x1 - x3) - y1) % P
    return (x3, y3)


def mul(k, pt):
    r = None
    while k:
        if k & 1:
            r = add(r, pt)
        pt = add(pt, pt)
        k >>= 1
    return r


def parse_der_sig(der: bytes):
    i = 0
    if der[i] != 0x30:
        raise ValueError("not SEQUENCE")
    i += 1
    ln = der[i]
    i += 1
    if ln & 0x80:
        cnt = ln & 0x7F
        ln = int.from_bytes(der[i:i + cnt], "big")
        i += cnt
    if der[i] != 0x02:
        raise ValueError("not INTEGER r")
    i += 1
    rlen = der[i]
    i += 1
    r = int.from_bytes(der[i:i + rlen], "big")
    i += rlen
    if der[i] != 0x02:
        raise ValueError("not INTEGER s")
    i += 1
    slen = der[i]
    i += 1
    s = int.from_bytes(der[i:i + slen], "big")
    return r, s


def pubkey_from_pem(pem: str) -> tuple:
    b64 = "".join(l for l in pem.strip().splitlines() if "-----" not in l)
    der = base64.b64decode(b64)
    if der[-65] != 0x04:
        raise ValueError("unexpected SPKI layout (不是未压缩点)")
    x = int.from_bytes(der[-64:-32], "big")
    y = int.from_bytes(der[-32:], "big")
    return (x, y)


def ecdsa_verify(pub, msg: bytes, der_sig: bytes) -> bool:
    r, s = parse_der_sig(der_sig)
    if not (1 <= r < N and 1 <= s < N):
        return False
    e = int.from_bytes(hashlib.sha256(msg).digest(), "big")
    w = pow(s, -1, N)
    u1 = e * w % N
    u2 = r * w % N
    pt = add(mul(u1, G), mul(u2, pub))
    if pt is None:
        return False
    return pt[0] % N == r


def h_leaf(data: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + data).digest()


def h_child(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def root_from_path(leaf: bytes, index: int, path: list, tree_size: int) -> bytes:
    fn, sn = index, tree_size - 1
    r = leaf
    for p in path:
        if fn % 2 == 1 or fn == sn:
            r = h_child(p, r)
            while fn % 2 == 0 and fn != 0:
                fn >>= 1
                sn >>= 1
        else:
            r = h_child(r, p)
        fn >>= 1
        sn >>= 1
    if sn != 0:
        raise ValueError(f"路径不足 sn={sn}")
    return r


def check_inclusion(rec: dict) -> dict:
    proof = rec["verification"]["inclusionProof"]
    leaf = h_leaf(base64.b64decode(rec["body"]))
    root = root_from_path(leaf, int(proof["logIndex"]), [bytes.fromhex(x) for x in proof["hashes"]],
                          int(proof["treeSize"]))
    return {
        "ok": root == bytes.fromhex(proof["rootHash"]),
        "logIndex": int(proof["logIndex"]),
        "record_logIndex": int(rec.get("logIndex", -1)),
        "treeSize": int(proof["treeSize"]),
        "depth": len(proof["hashes"]),
    }


def check_checkpoint(cp_text: str, pub) -> dict:
    """Go note 格式：正文 + '\\n\\n— name <b64:4字节keyhash||DER签名>'。文本边界有变体，逐种试。"""
    if "\n\n— " not in cp_text:
        return {"ok": False, "reason": "NO_SIGNATURE_BLOCK", "variant": None}
    body, sig_block = cp_text.split("\n\n— ", 1)
    parts = sig_block.strip().split()
    if len(parts) < 2:
        return {"ok": False, "reason": "BAD_SIG_BLOCK", "variant": None}
    sig_b64 = parts[-1]
    raw = base64.b64decode(sig_b64)
    der = raw[4:]  # 前 4 字节是 key hash
    for name, text in [("body+LF", body + "\n"), ("body", body), ("body+LF+LF", body + "\n\n")]:
        try:
            if ecdsa_verify(pub, text.encode(), der):
                return {"ok": True, "reason": "OK", "variant": name, "keyhash": raw[:4].hex()}
        except Exception:
            continue
    return {"ok": False, "reason": "SIGNATURE_MISMATCH", "variant": None}


def payload_hash_of(rec: dict) -> str:
    body = json.loads(base64.b64decode(rec["body"]))
    spec = body.get("spec") or {}
    for key in ("payloadHash", "data", "artifactHash"):
        node = spec.get(key)
        if isinstance(node, dict) and "value" in node:
            return node["value"].lower()
        if isinstance(node, dict) and "hash" in node and isinstance(node["hash"], dict):
            return node["hash"].get("value", "").lower()
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entry", required=True)
    ap.add_argument("--public-key", required=True, help="PEM 文件（Rekor /api/v1/log/publicKey 原文）")
    ap.add_argument("--receipt", default=None, help="回执 JSON；给了才做绑定校验")
    args = ap.parse_args()

    raw = json.load(open(args.entry, encoding="utf-8"))
    uuid = next(iter(raw))
    rec = raw[uuid]
    pub = pubkey_from_pem(open(args.public_key, encoding="utf-8").read())

    inc = check_inclusion(rec)
    cp = check_checkpoint(rec["verification"]["inclusionProof"]["checkpoint"], pub)

    bind = {"ok": None, "payload_hash": payload_hash_of(rec), "receipt_sha256": None}
    if args.receipt:
        r = json.load(open(args.receipt, encoding="utf-8"))
        rs = r.get("receipt_self_sha256")
        bind["receipt_sha256"] = rs
        bind["ok"] = (rs == bind["payload_hash"]) if rs else False

    print("ANCHOR_REPORT")
    print(f"  inclusion      = {'OK' if inc['ok'] else 'FAIL'}  (logIndex={inc['logIndex']}, "
          f"record_logIndex={inc['record_logIndex']}, treeSize={inc['treeSize']}, depth={inc['depth']})")
    print(f"  checkpoint_sig = {cp['reason']}" + (f"  (variant={cp['variant']}, keyhash={cp['keyhash']})" if cp["ok"] else ""))
    print(f"  binding        = " + ("NOT_CHECKED" if bind["ok"] is None else
                                     ("OK" if bind["ok"] else f"MISMATCH entry={bind['payload_hash'][:16]} receipt={str(bind['receipt_sha256'])[:16]}")))
    if inc["logIndex"] != inc["record_logIndex"]:
        print(f"  WARN           = 条目 record.logIndex 与 proof.logIndex 不一致，需记待核")
    print("  NOT_IMPLEMENTED= SET 签名 / logID↔公钥登记校验")

    ok = inc["ok"] and cp["ok"] and (bind["ok"] is not False)
    print("\nANCHOR_" + ("VERIFIED" if ok else "INCOMPLETE"))
    return 0 if ok else 5


if __name__ == "__main__":
    sys.exit(main())
