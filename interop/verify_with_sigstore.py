#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_with_sigstore.py —— 用 sigstore 官方库（3.6.5）自己的实现验我们的 S-0001 条目。

为什么这条值得做：
S-0001 的三项判据（inclusion / SET / checkpoint）此前**全部由我们手写代码算出**——
手写 P-256、手写 RFC 6962、手写 note 验签。口径上那只能算"同一操作者的自洽"。
把 sigstore 官方库拉进来跑同一份条目，就多一条"另一套代码、另一批作者"的对照：
即使仍跑在同一台机器，也不是同一支笔算出来的。这跟"我自己再跑一遍"不是一回事。

口径：这仍**不是 T1**（第三方实测须无关系的人亲自跑），只是 T4 里的"跨实现对照"。
"""
from __future__ import annotations

import json
import sys
import time


def main() -> int:
    import importlib.metadata as md
    import sigstore.models
    from sigstore._internal.trust import KeyringPurpose, TrustedRoot
    from sigstore.models import LogEntry

    print("sigstore 版本：", md.version("sigstore"))

    raw = json.load(open("out/rekor_statement_entry.json", encoding="utf-8"))
    resp = raw["response"]                       # {uuid: {body, integratedTime, ...}}
    uuid, rec = next(iter(resp.items()))
    prog = rec["verification"]["inclusionProof"]
    print("uuid：", uuid[:32] + "…")
    print("logIndex(record)：", rec["logIndex"], "| logIndex(proof)：", prog["logIndex"],
          "（不等属 Rekor API 已知语义，见 A4 记录）")
    print("treeSize：", prog["treeSize"], "| rootHash：", prog["rootHash"])
    print("proof hashes：", len(prog.get("hashes", [])), "| checkpoint 首行：",
          prog["checkpoint"].split("\n")[0])

    # ① 用官方自己的解析器把 Rekor API 响应读成 LogEntry（不是我们手拼字段）
    entry = LogEntry._from_response(resp)
    print("\nLogEntry 解出：log_index=%s body=%d 字节(b64) SET=%s"
          % (entry.log_index, len(entry.body), "有" if entry.inclusion_promise else "无"))

    # ② 拿 sigstore 官方信任根里的 Rekor 公钥
    # 说明：常规路径 TrustedRoot.production() 要在本机建 TUF 缓存目录，本机非管理员
    # 卡在 symlink（WinError 1314 / 5，与早先 python-tuf 那次同一死路）。
    # 但 sigstore 发行包里自带官方 trusted_root.json（_store/prod/），直接用它——
    # 既不是我们手拼的信任根，也不是从第三方镜像捡的。
    import pathlib

    import sigstore._store as _store
    tr_path = pathlib.Path(_store.__path__[0]) / "prod" / "trusted_root.json"
    tr = TrustedRoot.from_file(str(tr_path))
    print("信任根：sigstore 包内官方 %s（%d 字节）"
          % (tr_path.name, tr_path.stat().st_size))
    keyring = tr.rekor_keyring(KeyringPurpose.VERIFY)
    print("Rekor KeyID：", [k.key_id.hex()[:16] for k in keyring._keyring.values()])

    results = {}
    for label, fn in [
        ("merkle_inclusion", lambda: sigstore.models.verify_merkle_inclusion(entry)),
        ("checkpoint", lambda: sigstore.models.verify_checkpoint(keyring, entry)),
        ("set(签名条目时间戳)", lambda: entry._verify_set(keyring)),
        ("full(_verify)", lambda: entry._verify(keyring)),
    ]:
        t0 = time.perf_counter()
        try:
            fn()
            results[label] = {"ok": True, "ms": round((time.perf_counter() - t0) * 1e3, 1)}
            print("  %-16s OK   %.1f ms" % (label, results[label]["ms"]))
        except Exception as e:  # noqa: BLE001
            results[label] = {"ok": False, "err": type(e).__name__ + ": " + str(e)[:120],
                              "ms": round((time.perf_counter() - t0) * 1e3, 1)}
            print("  %-16s FAIL %s: %s" % (label, type(e).__name__, str(e)[:120]))

    # ③ 负向：rootHash 翻一位、SET 翻一位，官方实现都必须拒
    neg = {}
    import copy
    bad = copy.deepcopy(resp)
    bad[list(bad)[0]]["verification"]["inclusionProof"]["rootHash"] = \
        ("1" if bad[list(bad)[0]]["verification"]["inclusionProof"]["rootHash"][0] != "1" else "0") + \
        bad[list(bad)[0]]["verification"]["inclusionProof"]["rootHash"][1:]
    try:
        sigstore.models.verify_merkle_inclusion(LogEntry._from_response(bad))
        neg["root_hash_flip"] = "NOT REJECTED"
    except Exception as e:  # noqa: BLE001
        neg["root_hash_flip"] = "rejected (" + type(e).__name__ + ")"

    bad2 = copy.deepcopy(resp)
    k = list(bad2)[0]
    setv = bad2[k]["verification"]["signedEntryTimestamp"]
    bad2[k]["verification"]["signedEntryTimestamp"] = \
        ("A" if setv[0] != "A" else "B") + setv[1:]
    try:
        LogEntry._from_response(bad2)._verify(keyring)
        neg["set_flip"] = "NOT REJECTED"
    except Exception as e:  # noqa: BLE001
        neg["set_flip"] = "rejected (" + type(e).__name__ + ")"

    for kk, vv in neg.items():
        print("  负向 %-15s %s" % (kk, vv))

    pos_ok = all(results[k]["ok"] for k in results)
    neg_ok = all(v.startswith("rejected") for v in neg.values())
    verdict = "SIGSTORE_OFFICIAL_VERIFY_OK" if (pos_ok and neg_ok) else "CHECK"
    print("\nVERDICT:", verdict)

    json.dump({"sigstore_version": md.version("sigstore"), "verdict": verdict,
               "positive": results, "negative": neg,
               "log_index_record": rec["logIndex"], "log_index_proof": prog["logIndex"],
               "tree_size": prog["treeSize"], "root_hash": prog["rootHash"],
               "hashes": len(prog.get("hashes", []))},
              open("out/sigstore_crosscheck.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return 0 if verdict.endswith("OK") else 1


if __name__ == "__main__":
    sys.exit(main())
