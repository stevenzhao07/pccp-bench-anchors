#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
scitt_view.py —— 把一条 Rekor 条目翻译成"收据（receipt）语义"，并当场自验。

为什么要有这一层：SCITT 的概括是 statement + transparency service + receipt 三件套。
我们手上是 Rekor 的 hashedrekord，它不是原生 COSE Receipt —— 直接说"我们符合 SCITT"
是撒谎；什么都不做又等于把事实埋在自家脚本里。所以做成**显式映射**：

  输出的 JSON 里第一句就写清 "native_cose_receipt": false, "mapping": "rekor_entry_as_receipt_v1"

映射规约（这是本文件唯一的实质约定，其它人照此就能重算）：
  statement.subject_sha256  ← spec.data.hash.value
  statement.media_type      ← spec.data.hash.algorithm
  ts.uri                    ← https://rekor.sigstore.dev
  ts.log_id                 ← 条目的 logID
  receipt.leaf_index        ← 条目的 logIndex
  receipt.tree_size         ← verification.inclusionProof.treeSize
  receipt.root_hash         ← verification.inclusionProof.rootHash
  receipt.inclusion_path    ← verification.inclusionProof.hashes
  receipt.checkpoint        ← verification.inclusionProof.checkpoint（签名者 = 日志公钥）
  receipt.set               ← verification.signedEntryTimestamp（签名者 = 日志公钥）
  不在映射里的：signature（提交者的 Fulcio 签名，属 statement 归属，不属收据）

自验四项（全部复用 verify_zero_dep 的纯标准库函数，零第三方依赖）：
  1 STATEMENT   产物字节 sha256 == statement.subject_sha256（给了 --artifact 才查）
  2 INCLUSION   leaf_index + path + tree_size → root_hash
  3 CHECKPOINT  checkpoint 签名（日志公钥）
  4 SET         条目规范化 JSON 签名（日志公钥）

用法：
  python scitt_view.py --entry out\anchor_entry_A0003.json --rekor-key out\rekor_publicKey.json \
      --artifact <产物> --out out\scitt_view_A0003.json
"""
import argparse
import base64
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import verify_zero_dep as zd  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entry", required=True)
    ap.add_argument("--rekor-key", required=True)
    ap.add_argument("--artifact")
    ap.add_argument("--ts-uri", default="https://rekor.sigstore.dev")
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    entry = json.load(open(a.entry, "r", encoding="utf-8"))
    body = entry["body"]
    spec = json.loads(base64.b64decode(body)) if isinstance(body, str) else body
    proof = entry["verification"]["inclusionProof"]
    pub = zd.pub_from_rekor_pem(open(a.rekor_key, "r", encoding="utf-8").read())

    view = {
        "_mapping": "rekor_entry_as_receipt_v1",
        "_native_cose_receipt": False,
        "_disclosure": "本文件是 Rekor 条目对 SCITT receipt 语义的显式映射，不是 Transparency Service 原生签发的 COSE Receipt。字段可逐项重算，映射规约见 scitt_view.py 文件头。",
        "statement": {
            "media_type": spec["spec"]["data"]["hash"]["algorithm"],
            "subject_sha256": spec["spec"]["data"]["hash"]["value"],
            "kind": spec.get("kind"),
            "api_version": spec.get("apiVersion"),
        },
        "ts": {"uri": a.ts_uri, "log_id": entry["logID"]},
        "receipt": {
            "type": "rekor-inclusion+set",
            "leaf_index": proof["logIndex"],
            "declared_log_index": entry["logIndex"],
            "tree_size": proof["treeSize"],
            "root_hash": proof["rootHash"],
            "inclusion_path": proof["hashes"],
            "path_len": len(proof["hashes"]),
            "checkpoint": proof["checkpoint"],
            "set": entry["verification"]["signedEntryTimestamp"],
            "integrated_time": entry.get("integratedTime"),
        },
        "provenance": {
            "_note": "以下字段不属收据，属 statement 归属；这里只照抄，不由本工具验证",
            "submitter_signature": spec["spec"].get("signature", {}).get("content"),
            "submitter_public_key": spec["spec"].get("signature", {}).get("publicKey"),
        },
        "checks": {},
    }

    checks = view["checks"]

    if a.artifact:
        h = hashlib.sha256(open(a.artifact, "rb").read()).hexdigest()
        checks["STATEMENT"] = "OK" if h == view["statement"]["subject_sha256"] else "FAIL"
        view["statement"]["artifact_bytes"] = os.path.getsize(a.artifact)
    else:
        checks["STATEMENT"] = "SKIP"

    checks["INCLUSION"] = "OK" if zd.check_inclusion(entry) else "FAIL"
    checks["CHECKPOINT"] = "OK" if zd.check_checkpoint(entry, pub) else "FAIL"
    checks["SET"] = "OK" if zd.check_set(entry, pub) else "FAIL"

    overall = "ALL_PASS" if all(v in ("OK", "SKIP") for v in checks.values()) else "HAS_FAIL"
    view["overall"] = overall

    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(view, f, ensure_ascii=False, indent=2)

    if a.json:
        print(json.dumps(view, ensure_ascii=False, indent=2))
    else:
        print("SCITT_VIEW (mapping = rekor_entry_as_receipt_v1, native COSE receipt = false)")
        print(f"  leaf_index     {view['receipt']['leaf_index']}   (declared {view['receipt']['declared_log_index']})")
        print(f"  tree_size      {view['receipt']['tree_size']}")
        print(f"  path_len       {view['receipt']['path_len']}")
        for k, v in checks.items():
            print(f"  {k:<14} {v}")
        print(overall)
    return 0 if overall == "ALL_PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
