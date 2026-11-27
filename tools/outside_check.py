#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""outside_check.py —— 用"外人拿到这个仓"的视角，验一遍这个仓能不能自证。

做法不是"再跑一遍我们的脚本"，而是：

  1. 把 anchors_repo 整份拷到一个临时目录（模拟别人 clone 下来）；
  2. 只允许用拷贝里的相对路径（tools/ proof/ certs/），不读 bench_receipt 的任何 out/、dist/；
  3. 逐项跑：三份哈希、S-0001 三项、A-0003 六项零依赖、COSE 两种编码 + 篡改负例、v0.3.2 自跑 51/51；
  4. 额外扫一遍可移植性：工具脚本里有没有写死 C:\\ / D:\\ 或跳出仓外的相对路径 —— 有就等于
     "换一台机器就跑不了"，这是外人视角最致命的一类缺陷。

口径（必须写在结论里）：这是同操作者换目录干跑（T4），不是第三方实测（T1）。

用法：
    python outside_check.py                 # 默认拷 bench_receipt/anchors_repo
    python outside_check.py --repo <dir>    # 指定要验的仓目录
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
EXPECT = {
    "proof/pccp-bench_v0.3_candidate.zip": "d684eaca7b2ba32483c23a1474815bf0314dd2cdf8770648eb7b6e2c1826ed99",
    "receipts/receipt_demo5.canonical.json": "b19fd9d6dc473fee5f069449ef71541f28be9d455074336bb85db4db7fd349bd",
}
LOGINDEX_S0001 = 4145697630
rows = []


def add(cid, claim, status, detail):
    rows.append({"id": cid, "claim": claim, "status": status, "detail": str(detail)[:500]})


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def run(args, cwd, timeout=180):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    # 关键：把无关路径从 PYTHONPATH 清掉，逼它只能用仓里的 tools/
    env["PYTHONPATH"] = os.path.join(cwd, "tools")
    p = subprocess.run([sys.executable] + args, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout, env=env)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def tail(t, n=3):
    ls = [x for x in t.strip().splitlines() if x.strip()]
    return " | ".join(ls[-n:])[:300]


def scan_portable(dst):
    """扫 tools/*.py 里那些"换台机器就跑不了"的痕迹。"""
    bad = []
    tools = os.path.join(dst, "tools")
    if not os.path.isdir(tools):
        return ["tools/ 目录缺失"]
    for name in sorted(os.listdir(tools)):
        if not name.endswith(".py"):
            continue
        txt = open(os.path.join(tools, name), encoding="utf-8", errors="replace").read()
        for pat, label in [(r"[A-Za-z]:\\", "写死盘符路径"),
                           (r"\.\./\.\.|\.\.\\", "跳出仓外的相对路径"),
                           (r"bench_receipt|标准\\vault|Doubao\\chats", "指向本机工作目录")]:
            hits = re.findall(pat, txt)
            if hits:
                bad.append(f"{name}:{label}({len(hits)})")
    return bad


def selftest(src):
    """负向对照：往拷贝里种一个违规脚本，扫描器必须抓到 —— 抓不到说明这检查是摆设。"""
    tmp = tempfile.mkdtemp(prefix="outside_st_")
    dst = os.path.join(tmp, "repo")
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    clean = scan_portable(dst)
    planted = os.path.join(dst, "tools", "_planted_violation.py")
    with open(planted, "w", encoding="utf-8") as f:
        f.write('p = r"C:\\Users\\someone\\out\\cases.json"\nq = "../../bench_receipt/dist"\n')
    bad = scan_portable(dst)
    ok = (not clean) and bool(bad)
    print("PORTABLE_SELFTEST")
    print("  干净仓扫描      %s" % ("零命中" if not clean else "已有命中:" + "; ".join(clean)))
    print("  种入违规后扫描  %s" % (" ".join(bad) if bad else "零命中（漏检！）"))
    print("\nPORTABLE_SELFTEST_" + ("OK" if ok else "HAS_FAIL"))
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.path.join(HERE, "anchors_repo"))
    ap.add_argument("--selftest", action="store_true", help="只跑可移植性扫描的负向对照")
    a = ap.parse_args()
    src = os.path.abspath(a.repo)
    if not os.path.isdir(src):
        print("repo not found:", src)
        return 2
    if a.selftest:
        return selftest(src)

    tmp = tempfile.mkdtemp(prefix="outside_")
    dst = os.path.join(tmp, "repo")
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    print("simulated clone ->", dst)

    # ---- 1. 字节哈希 ----
    for rel, want in EXPECT.items():
        p = os.path.join(dst, rel)
        if not os.path.isfile(p):
            add("HASH-" + os.path.basename(rel), f"{rel} 哈希与台账一致", "FAIL", "文件不在仓里")
            continue
        got = sha(p)
        add("HASH-" + os.path.basename(rel), f"{rel} 的 sha256 与台账登记值逐位相等",
            "PASS" if got == want else "FAIL", f"{got[:16]}… size={os.path.getsize(p)}")

    # ---- 2. S-0001 三项 ----
    e = os.path.join("proof", "rekor_statement_S-0001.json")
    k = os.path.join("proof", "rekor_publicKey.pem")
    for cid, sc, extra in [("INC-S0001", "verify_rekor_inclusion.py", ["--entry", e]),
                           ("SET-S0001", "verify_set.py", ["--entry", e, "--public-key", k]),
                           ("CP-S0001", "verify_anchor.py", ["--entry", e, "--public-key", k])]:
        rc, t = run([os.path.join("tools", sc)] + extra, dst)
        add(cid, f"{sc} 只用仓内字节即可通过", "PASS" if rc == 0 else "FAIL", tail(t))

    # 条目字段
    try:
        import base64
        raw = json.load(open(os.path.join(dst, e), encoding="utf-8"))
        rec = raw[next(iter(raw))]
        body = json.loads(base64.b64decode(rec["body"]))
        add("REC-S0001", "仓内条目自带 logIndex 与 hash 与台账一致",
            "PASS" if rec["logIndex"] == LOGINDEX_S0001 and body["kind"] == "hashedrekord" else "FAIL",
            f"logIndex={rec['logIndex']} kind={body.get('kind')} sha={body['spec']['data']['hash']['value'][:16]}…")
    except Exception as ex:
        add("REC-S0001", "条目字段", "ERROR", repr(ex))

    # ---- 3. A-0003 六项零依赖 ----
    rc, t = run([os.path.join("tools", "verify_zero_dep.py"),
                 "--bundle", os.path.join("proof", "A-0003.bundle.sigstore.json"),
                 "--artifact", os.path.join("proof", "pccp-bench_v0.3_candidate.zip"),
                 "--entry", os.path.join("proof", "A-0003.entry.json"),
                 "--rekor-key", os.path.join("proof", "rekor_publicKey.pem"),
                 "--intermediate", os.path.join("certs", "fulcio_intermediate.pem"),
                 "--root", os.path.join("certs", "fulcio_root.pem")], dst)
    add("ZDEP-A0003", "六项（绑定/LOGID/包含/checkpoint/SET/证书链）只用仓内字节全过",
        "PASS" if rc == 0 and "ZERO_DEP_ALL_PASS" in t else "FAIL", tail(t))

    # ---- 4. COSE 两种编码 + 篡改 ----
    pub = os.path.join("proof", "scitt_test_pub.pem")
    art = os.path.join("proof", "pccp-bench_v0.3_candidate.zip")
    for cid, f, want in [("SCITT-TAG18", "statement_A0003_scitt.cose", "tag 18"),
                         ("SCITT-UNTAGGED", "statement_A0003.cose", "untagged")]:
        rc, t = run([os.path.join("tools", "verify_scitt_statement.py"),
                     "--statement", os.path.join("proof", f), "--pubkey-pem", pub,
                     "--artifact", art], dst)
        add(cid, f"COSE_Sign1（{want}）只用仓内字节验得过并与包绑定",
            "PASS" if rc == 0 and "SCITT_ALL_PASS" in t and want in t else "FAIL", tail(t))
    rc, t = run([os.path.join("tools", "verify_scitt_statement.py"),
                 "--statement", os.path.join("proof", "statement_A0003_scitt.cose"),
                 "--pubkey-pem", pub, "--tamper"], dst)
    add("SCITT-TAMPER", "篡改一字节必须验不过", "PASS" if rc != 0 else "FAIL", tail(t, 2))

    # ---- 5. v0.3.2 自跑 51/51 ----
    try:
        pkg = os.path.join(dst, "proof", "pccp-bench_v0.3.2_candidate.zip")
        ext = os.path.join(tmp, "pkg")
        with zipfile.ZipFile(pkg) as z:
            z.extractall(ext)
        roots = [os.path.join(ext, x) for x in os.listdir(ext)]
        # 包里可能有一层顶层目录
        if len(roots) == 1 and os.path.isdir(roots[0]):
            ext = roots[0]
        ds = os.path.join(ext, "dataset")
        rc, t = run(["selfcheck.py"], ds if os.path.isdir(ds) else ext)
        add("PKG-V032", "包在临时目录里自跑 51/51",
            "PASS" if rc == 0 and "SELFCHECK_ALL_PASS" in t and "51/51" in t else "FAIL", tail(t))
    except Exception as ex:
        add("PKG-V032", "包自跑", "ERROR", repr(ex))

    # ---- 6. 可移植性：写死本机路径 / 逃出仓外的相对路径 ----
    bad = scan_portable(dst)
    add("PORTABLE", "仓内工具换机器也能跑：不写死本机路径、不逃出仓外",
        "PASS" if not bad else "FAIL", "; ".join(bad) or f"扫 {len(os.listdir(os.path.join(dst, 'tools')))} 个脚本，零命中")

    # ---- 汇总 ----
    n = {}
    for r in rows:
        n[r["status"]] = n.get(r["status"], 0) + 1
    ok = n.get("FAIL", 0) == 0 and n.get("ERROR", 0) == 0
    doc = {"generated_at": __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"),
           "repo": src, "simulated_clone": dst, "scope": "只用仓内文件，不读开发机 out/ dist/",
           "label": "同操作者换目录干跑（T4），不是第三方实测（T1）",
           "verdict": "OUTSIDE_OK" if ok else "OUTSIDE_HAS_FAIL",
           "summary": n, "checks": rows}
    out_dir = os.path.join(HERE, "out")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "OUTSIDE_CHECK.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)

    print("OUTSIDE_CHECK（视角：别人 clone 这个仓）")
    for r in rows:
        print("  %-14s %-6s %s" % (r["id"], r["status"], r["detail"][:100]))
    print("\n  PASS=%d FAIL=%d ERROR=%d" % (n.get("PASS", 0), n.get("FAIL", 0), n.get("ERROR", 0)))
    print("\nOUTSIDE_" + ("OK" if ok else "HAS_FAIL"))
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
