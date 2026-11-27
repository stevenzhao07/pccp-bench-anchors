#!/usr/bin/env python3
"""verify_rekor_inclusion.py — 纯标准库验证 Rekor 透明日志的 Merkle 包含性证明。

为什么自己写：把"锚定"这件事验到不需要 sigstore SDK、不需要联网也能复核。
验的是 RFC 6962 §2.1.1 的审计路径：leaf → path → root，且 root 必须等于日志树根。

用法：
  python verify_rekor_inclusion.py --entry entry.json [--public-key publicKey.pem]

边界（必须写进报告）：
- 本工具验 **包含性**（条目确实在某棵树里、且路径可重算到同一 root）。
- 本工具**不验** checkpoint 签名（需 Rekor 公钥 + ECDSA），也**不验** SET（signedEntryTimestamp）。
  两者都是"未实现"，不是"已通过"。
"""
import argparse
import base64
import hashlib
import json
import sys


def h_leaf(data: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + data).digest()


def h_child(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def root_from_path(leaf: bytes, index: int, path: list[bytes], tree_size: int) -> bytes:
    """RFC 6962 Merkle 审计路径重算。"""
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
        raise ValueError(f"审计路径长度不足，剩 sn={sn}")
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entry", required=True, help="Rekor /api/v1/log/entries 返回的 JSON")
    ap.add_argument("--public-key", default=None, help="（未实现签名校验）仅记录路径")
    args = ap.parse_args()

    with open(args.entry, encoding="utf-8") as f:
        raw = json.load(f)

    # 响应形如 {"<uuid>": {entry...}}
    uuid = next(iter(raw))
    rec = raw[uuid]
    body_b64 = rec["body"]
    body = base64.b64decode(body_b64)
    proof = rec["verification"]["inclusionProof"]
    tree_size = int(proof["treeSize"])
    log_index = int(proof.get("logIndex", rec.get("logIndex", -1)))
    path = [bytes.fromhex(x) for x in proof["hashes"]]
    root_expected = bytes.fromhex(proof["rootHash"])

    leaf = h_leaf(body)
    root_actual = root_from_path(leaf, log_index, path, tree_size)

    ok = root_actual == root_expected
    print("REKOR_INCLUSION_" + ("VERIFIED" if ok else "MISMATCH"))
    print(f"  uuid          = {uuid}")
    print(f"  logIndex      = {log_index}")
    print(f"  treeSize      = {tree_size}")
    print(f"  leafHash      = {leaf.hex()}")
    print(f"  root(expected)= {root_expected.hex()}")
    print(f"  root(computed)= {root_actual.hex()}")
    print(f"  pathDepth     = {len(path)}")
    print(f"  checkpoint    = {str(proof.get('checkpoint', ''))[:60]}...")
    print("  NOT_CHECKED   = checkpoint 签名 / SET 签名（未实现，不得称为已通过）")
    return 0 if ok else 4


if __name__ == "__main__":
    sys.exit(main())
