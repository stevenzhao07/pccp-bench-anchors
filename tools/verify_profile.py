#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
verify_profile.py —— 让自述 profile 不能漂移。

问题：`scitt_profile.json` 里每条 claimed 都写着 "status: PASS (本机，T4)"。
但那句话是我手写的。手写的状态会过期：工具改了、产物换了、文件壳变了，
profile 还挂着 "PASS"，等于自述替事实背书。

做法：profile 里每条 claimed 必须能被**实测**复现。本脚本把这些条目逐条跑一遍，
拿实测结果和 profile 里写的比：
  写得 PASS 但不复现 → PROFILE_DRIFT（这是最该抓的一种）
  写得 NOT_CLAIMED 但居然能复现 → 也报（说明 profile 保守过头，同样是不一致）

六条检查（C1–C5 对应 profile 的 claimed，C6 是负向可控）：
  C1 产物摘要 → Statement 的 subject_sha256（verify_scitt_statement STATEMENT）
  C2 COSE_Sign1 + 零依赖验签（SCITT_ALL_PASS）
  C3 位置可独立重算（scitt_view INCLUSION）
  C4 日志两道签名（scitt_view CHECKPOINT + SET）
  C5 一条命令全矩阵（verify_all 八行 ALL_PASS）
  C6 负向可控：产物翻一字节 → verify_all 必须 HAS_FAIL 且退出码 1

为什么 C6 一定要有：前五条都是"能通过"，只有负向能证明这些判据不是永远通过。

用法：
  python verify_profile.py --entry out\anchor_entry_A0003.json \
      --rekor-key out\rekor_publicKey.json \
      --bundle out\anchor_A0003.bundle.sigstore.json \
      --artifact <产物> --statement out\statement_A0003.cose \
      --statement-pubkey out/scitt_test_pub.pem --profile scitt_profile.json
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def run(script, args):
    p = subprocess.run([PY, os.path.join(HERE, script)] + args,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entry", required=True)
    ap.add_argument("--rekor-key", required=True)
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--artifact", required=True)
    ap.add_argument("--statement", required=True)
    ap.add_argument("--statement-pubkey", required=True)
    ap.add_argument("--profile", default=os.path.join(HERE, "scitt_profile.json"))
    ap.add_argument("--integrated-time", type=int)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    prof = json.load(open(a.profile, encoding="utf-8"))
    claimed = {c["id"]: c for c in prof["conformance"]["claimed"]}

    measured = {}

    # C1 + C2：一次 statement 验签就能同时给出摘要绑定与签名两项
    rc, out = run("verify_scitt_statement.py",
                  ["--statement", a.statement, "--pubkey-pem", a.statement_pubkey,
                   "--artifact", a.artifact])
    measured["C1"] = "PASS" if ("SIGNATURE      OK" in out and "BINDING        OK" in out) else "FAIL"
    measured["C2"] = "PASS" if "SCITT_ALL_PASS" in out and "ALG            -7" in out else "FAIL"

    # C3 + C4：收据语义视图的三项
    rc, out = run("scitt_view.py",
                  ["--entry", a.entry, "--rekor-key", a.rekor_key, "--artifact", a.artifact])
    measured["C3"] = "PASS" if (re.search(r"INCLUSION\s+OK", out) and "STATEMENT      OK" in out) else "FAIL"
    measured["C4"] = "PASS" if (re.search(r"CHECKPOINT\s+OK", out) and re.search(r"SET\s+OK", out)) else "FAIL"

    # C5：整条命令
    allargs = ["--entry", a.entry, "--public-key", a.rekor_key, "--bundle", a.bundle,
               "--artifact", a.artifact, "--statement", a.statement,
               "--statement-pubkey", a.statement_pubkey]
    if a.integrated_time:
        allargs += ["--integrated-time", str(a.integrated_time)]
    rc, out = run("verify_all.py", allargs)
    n_rows = len(re.findall(r"\n(?=(?:LOGID_BINDING|INCLUSION|CHECKPOINT|SET|BINDING|CHAIN|SCITT_STATEMENT|RECEIPT_VIEW))", out))
    measured["C5"] = "PASS" if ("ALL_PASS" in out and rc == 0 and n_rows >= 8) else "FAIL"

    # C6：负向可控（临时把产物改一个字节，不改原件）
    tmp = os.path.join(tempfile.gettempdir(), "_profile_tamper.bin")
    data = bytearray(open(a.artifact, "rb").read())
    data[0] ^= 0x01
    open(tmp, "wb").write(bytes(data))
    nargs = [x for x in allargs]
    nargs[nargs.index(a.artifact)] = tmp
    rc, out = run("verify_all.py", nargs)
    measured["C6"] = "PASS" if ("HAS_FAIL" in out and rc == 1) else "FAIL"
    try:
        os.remove(tmp)
    except OSError:
        pass

    rows = []
    drift = 0
    for cid in sorted(measured):
        m = measured[cid]
        if cid in claimed:
            declared = claimed[cid].get("status", "")
            declared_pass = declared.upper().startswith("PASS")
            consistent = (m == "PASS") == declared_pass
            rows.append((cid, "PASS" if declared_pass else declared.split("(")[0].strip(), m,
                         "一致" if consistent else "DRIFT", claimed[cid]["claim"][:46]))
            if not consistent:
                drift += 1
        else:
            # profile 漏登记一条可复现的检查 → 同样是自述不完整
            rows.append((cid, "未声称", m, "DRIFT", "profile 未列，但这条检查实际存在"))
            drift += 1

    overall = "PROFILE_ALL_CONSISTENT" if drift == 0 else "PROFILE_DRIFT"

    if a.json:
        print(json.dumps({"overall": overall, "drift": drift,
                          "rows": [{"check": r[0], "declared": r[1], "measured": r[2],
                                    "verdict": r[3], "claim": r[4]} for r in rows]},
                         ensure_ascii=False, indent=2))
    else:
        print(f"{'检查':<6}{'profile 自述':<12}{'实测':<8}{'结论':<8}说明")
        print("-" * 78)
        for r in rows:
            print(f"{r[0]:<6}{r[1]:<12}{r[2]:<8}{r[3]:<8}{r[4]}")
        print("-" * 78)
        print(overall)
    return 0 if overall == "PROFILE_ALL_CONSISTENT" else 1


if __name__ == "__main__":
    sys.exit(main())
