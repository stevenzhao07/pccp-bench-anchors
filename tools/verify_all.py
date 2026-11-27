#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
verify_all.py —— 一条命令跑完六项判据，输出 PASS/FAIL 矩阵。

为什么要这个：前面每个判据都是独立脚本，外人要验一条记录得跑五个命令、还要自己
判断"哪个输出算通过"。那等于把判断权又收回给作者。这里把判据收成一条命令 + 一张表。

六项（各自独立，任一项失败都不算通过）：
  1  LOGID_BINDING      logID == SHA-256(SPKI DER)，且与远端现取公钥同一把钥匙
  2  INCLUSION          RFC 6962 自算路径 → 树根
  3  CHECKPOINT         checkpoint 正文签名（P-256）
  4  SET                条目规范化 JSON 签名（P-256）
  5  CHAIN              leaf ← intermediate ← root（Sigstore 官方信任根）
  6  BINDING            产物字节 sha256 == bundle digest == 条目 digest
  （给了 --receipt 与 --dataset/--engine 时追加第 7 项：回执本身十条判据）

用法：
  python verify_all.py --entry out\anchor_entry_A0002.json \
        --public-key out\rekor_publicKey.json \
        --bundle out\anchor_A0002.sigstore.json --artifact out\anchor_A0002_artifact.bin \
        --integrated-time 1795756228
"""
import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def run(script, args):
    p = subprocess.run([PY, os.path.join(HERE, script)] + args,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def find_status(text, keys):
    for k in keys:
        m = re.search(rf'"{k}":\s*"([A-Z_]+)"', text)
        if m:
            return m.group(1)
    return None


def normalize_entry(path):
    """Rekor 两种形态：raw（{uuid: rec}）与摊平（rec 本身）。
    老判据（verify_anchor/set/logid_binding）只吃 raw，零依赖判据只吃摊平。
    这里统一成 raw 交给老判据，摊平那份原样交给新判据 —— 不靠"记得用哪种文件"。"""
    d = json.load(open(path, encoding="utf-8"))
    if "body" in d and "verification" in d:      # 摊平形态
        tmp = os.path.join(os.environ.get("TEMP", "."), "_entry_raw_" + str(os.getpid()) + ".json")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"_flattened": d}, f)
        return path, tmp
    return path, path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entry", required=True)
    ap.add_argument("--public-key", required=True)
    ap.add_argument("--bundle")
    ap.add_argument("--artifact")
    ap.add_argument("--integrated-time", type=int)
    ap.add_argument("--expect-issuer", default="https://token.actions.githubusercontent.com")
    ap.add_argument("--expect-identity-regex")
    ap.add_argument("--receipt")
    ap.add_argument("--dataset")
    ap.add_argument("--engine")
    ap.add_argument("--statement", help="COSE_Sign1 签的 Signed Statement（SCITT 形状）")
    ap.add_argument("--statement-pubkey", help="验 statement 签名用的 PEM 公钥")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    rows = []   # (name, status, detail)
    flat_entry, raw_entry = normalize_entry(a.entry)

    rc, out = run("verify_logid_binding.py", ["--entry", raw_entry, "--public-key", a.public_key, "--live"])
    st = find_status(out, ["status"])
    rows.append(("LOGID_BINDING", st, "logID == SHA-256(SPKI DER); 远端公钥一致" if st == "LOGID_BOUND" else "") )

    rc, out = run("verify_anchor.py", ["--entry", raw_entry, "--public-key", a.public_key])
    inc_ok = "inclusion      = OK" in out
    cp_ok = "checkpoint_sig = OK" in out
    rows.append(("INCLUSION", "OK" if inc_ok else "FAIL", ""))
    rows.append(("CHECKPOINT", "OK" if cp_ok else "FAIL", ""))

    rc, out = run("verify_set.py", ["--entry", raw_entry, "--public-key", a.public_key])
    st = find_status(out, ["status"])
    rows.append(("SET", "OK" if st == "SET_VERIFIED" else "FAIL", ""))

    if a.bundle and a.artifact:
        rc, out = run("verify_bundle.py", ["--bundle", a.bundle, "--artifact", a.artifact,
                                           "--expect-issuer", a.expect_issuer]
                      + (["--expect-identity-regex", a.expect_identity_regex] if a.expect_identity_regex else []))
        st = find_status(out, ["status"])
        rows.append(("BINDING", "OK" if st == "BUNDLE_VERIFIED" else "FAIL",
                     "产物字节 == bundle digest == 条目 digest" if st == "BUNDLE_VERIFIED" else ""))

        ch_args = ["--bundle", a.bundle]
        if a.integrated_time:
            ch_args += ["--integrated-time", str(a.integrated_time)]
        rc, out = run("verify_fulcio_chain.py", ch_args)
        st = find_status(out, ["status"])
        rows.append(("CHAIN", "OK" if st == "FULCIO_CHAIN_VERIFIED" else "FAIL",
                     "leaf←intermediate←root；CT/SCT 未验" if st == "FULCIO_CHAIN_VERIFIED" else ""))

    if a.receipt and a.dataset and a.engine:
        rc, out = run("verify_receipt.py", ["--receipt", a.receipt, "--dataset", a.dataset,
                                            "--engine", a.engine, "--rekor-entry", raw_entry,
                                            "--public-key", a.public_key])
        st = find_status(out, ["status"])
        rows.append(("RECEIPT", "OK" if st == "RECEIPT_VALID" else "FAIL", ""))

    if a.statement and a.statement_pubkey:
        sa = ["--statement", a.statement, "--pubkey-pem", a.statement_pubkey]
        if a.artifact:
            sa += ["--artifact", a.artifact]
        rc, out = run("verify_scitt_statement.py", sa)
        rows.append(("SCITT_STATEMENT", "OK" if "SCITT_ALL_PASS" in out else "FAIL",
                     "COSE_Sign1 零依赖验签 + 载荷绑定" if "SCITT_ALL_PASS" in out else ""))

    # 收据语义视图：把 Rekor 条目映射成 receipt，并当场重算（不代表原生 COSE Receipt）
    sv = ["--entry", flat_entry, "--rekor-key", a.public_key]
    if a.artifact:
        sv += ["--artifact", a.artifact]
    rc, out = run("scitt_view.py", sv)
    rows.append(("RECEIPT_VIEW", "OK" if "ALL_PASS" in out else "FAIL",
                 "Rekor→receipt 显式映射（非原生 COSE Receipt）" if "ALL_PASS" in out else ""))

    overall = "ALL_PASS" if all(r[1] in ("OK", "LOGID_BOUND") for r in rows) else "HAS_FAIL"
    if a.json:
        print(json.dumps({"overall": overall,
                          "rows": [{"judgment": r[0], "status": r[1], "detail": r[2]} for r in rows]},
                         ensure_ascii=False, indent=2))
    else:
        print(f"{'判据':<18}{'结果':<13}说明")
        print("-" * 64)
        for name, status, detail in rows:
            print(f"{name:<18}{str(status):<13}{detail}")
        print("-" * 64)
        print(overall)
    return 0 if overall == "ALL_PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

