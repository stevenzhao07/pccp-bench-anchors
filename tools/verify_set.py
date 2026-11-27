#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_set.py —— 校验 Rekor 条目的 SET（signedEntryTimestamp）。

背景：之前所有校验里 SET 一直是"未实现"，只校验了包含性证明、checkpoint 签名和绑定。
SET 是日志对自己条目做的签名，意义与它们不同：
  - 包含性证明：证明"这条在树里"（路径可算，但路径是日志给的）
  - checkpoint：证明"当时的树根"（日志签的）
  - SET：证明"这条记录本身在 integratedTime 那一刻被日志签过"（针对这一条结构化字段）

Rekor 的做法：对条目四个字段的规范化 JSON 签名
    {"body": <body 原始字符串>, "integratedTime": <int>, "logID": <hex str>, "logIndex": <int>}
用 ECDSA P-256 + SHA-256，签名为 base64 编码的 DER（ASN.1 SEQUENCE{r,s}）。

本工具纯标准库实现（复用 verify_anchor.py 里的 P-256 验签），零依赖。
用法：
  python verify_set.py --entry out\\rekor_public_ours.json --public-key out\\rekor_publicKey.json
输出：SET_VERIFIED / SET_MISMATCH / SET_ERROR
"""
import argparse
import base64
import hashlib
import json
import sys

import verify_anchor as va


def canonical_candidates(entry: dict):
    """SET 的被签正文有几种可能的序列化，逐个试，全部失败才判错。
    不猜'哪个对'，而是把候选都验一遍并报告命中的是哪种——这样才算可归因。"""
    body = entry["body"]
    t = int(entry["integratedTime"])
    lid = entry["logID"]
    idx = int(entry["logIndex"])
    obj = {"body": body, "integratedTime": t, "logID": lid, "logIndex": idx}
    cands = []
    cands.append(("sorted-compact", json.dumps(obj, sort_keys=True, separators=(",", ":"))))
    cands.append(("insertion-compact", json.dumps(obj, separators=(",", ":"))))
    cands.append(("sorted-spaced", json.dumps(obj, sort_keys=True)))
    # body 若已被解析成对象（部分 API 返回 dict）
    if isinstance(body, dict):
        o2 = dict(obj, body=body)
        cands.append(("dictbody-sorted", json.dumps(o2, sort_keys=True, separators=(",", ":"))))
    return cands


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entry", required=True)
    ap.add_argument("--public-key", required=True)
    a = ap.parse_args()

    raw = json.load(open(a.entry, encoding="utf-8"))
    entry = raw[list(raw.keys())[0]] if isinstance(raw, dict) and a.entry.endswith(".json") \
        and "body" not in raw else raw
    if "verification" not in entry:
        print(json.dumps({"status": "SET_ERROR", "reason": "条目无 verification 段"}))
        return 2

    set_b64 = entry["verification"].get("signedEntryTimestamp")
    if set_b64:
        der = base64.b64decode(set_b64)
    elif "signedEntryTimestamp" in raw and isinstance(raw.get("signedEntryTimestamp"), str):
        der = base64.b64decode(raw["signedEntryTimestamp"])
    else:
        print(json.dumps({"status": "SET_ERROR", "reason": "条目无 SET"}))
        return 2

    pub = va.pubkey_from_pem(open(a.public_key, encoding="utf-8").read())
    hit = None
    for name, payload in canonical_candidates(entry):
        msg = payload.encode()
        if va.ecdsa_verify(pub, msg, der):
            hit = name
            break

    out = {
        "status": "SET_VERIFIED" if hit else "SET_MISMATCH",
        "canonicalization": hit,
        "logID": entry.get("logID"),
        "logIndex": entry.get("logIndex"),
        "integratedTime": entry.get("integratedTime"),
        "set_sha256": hashlib.sha256(der).hexdigest()[:16],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if hit else 1


if __name__ == "__main__":
    sys.exit(main())
