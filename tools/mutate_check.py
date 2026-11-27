#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mutate_check.py —— 给每一项检查做负向对照：改坏一处，对应的那项必须响。

上一轮只给"可移植性扫描"做了负向对照。这一轮把同样的纪律推到全部判据上：
对仓里的每一类字节证据做一次定向破坏，然后要求**指定的那一项**变成 FAIL。

为什么必须这么做：
  - 一个只会 PASS 的检查，和没有检查是一回事；
  - 只有"改坏 A 必须让 A 项失败、而不是让 B 项失败"，才能说明判据是对着的那一条。

每一条都在临时拷贝里做，不动仓里的原文件；跑完删目录。
口径：同操作者定向破坏（T4），证明的是"检查有灵敏度"，不证明任何第三方见证。

用法：
    python mutate_check.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "anchors_repo")
OUT = os.path.join(HERE, "out")


def run_outside(repo_dir, out_json):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, os.path.join(HERE, "outside_check.py"),
                        "--repo", repo_dir, "--out", out_json],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env, timeout=300)
    try:
        return p.returncode, json.load(open(out_json, encoding="utf-8"))
    except Exception:
        return p.returncode, None


# ---------- 定向破坏 ----------
def flip_hex(s):
    return ("0" if s[0] not in "0" else "1") + s[1:]


def m_hash(d):
    p = os.path.join(d, "proof", "pccp-bench_v0.3_candidate.zip")
    with open(p, "ab") as f:
        f.write(b"\x00")


def m_inc(d):
    p = os.path.join(d, "proof", "rekor_statement_S-0001.json")
    raw = json.load(open(p, encoding="utf-8"))
    rec = raw[next(iter(raw))]
    hashes = rec["verification"]["inclusionProof"]["hashes"]
    hashes[0] = flip_hex(hashes[0])
    json.dump(raw, open(p, "w", encoding="utf-8"), ensure_ascii=False)


def m_set(d):
    p = os.path.join(d, "proof", "rekor_statement_S-0001.json")
    raw = json.load(open(p, encoding="utf-8"))
    rec = raw[next(iter(raw))]
    s = rec["verification"]["signedEntryTimestamp"]
    rec["verification"]["signedEntryTimestamp"] = ("A" if s[0] != "A" else "B") + s[1:]
    json.dump(raw, open(p, "w", encoding="utf-8"), ensure_ascii=False)


def m_cp(d):
    p = os.path.join(d, "proof", "rekor_statement_S-0001.json")
    raw = json.load(open(p, encoding="utf-8"))
    rec = raw[next(iter(raw))]
    cp = rec["verification"]["inclusionProof"]["checkpoint"]
    # checkpoint 末尾是签名行，改它一个字符
    lines = cp.split("\n")
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip() and len(lines[i]) > 20:
            lines[i] = ("A" if lines[i][0] != "A" else "B") + lines[i][1:]
            break
    rec["verification"]["inclusionProof"]["checkpoint"] = "\n".join(lines)
    json.dump(raw, open(p, "w", encoding="utf-8"), ensure_ascii=False)


def m_rec(d):
    p = os.path.join(d, "proof", "rekor_statement_S-0001.json")
    raw = json.load(open(p, encoding="utf-8"))
    rec = raw[next(iter(raw))]
    rec["logIndex"] = rec["logIndex"] + 1
    json.dump(raw, open(p, "w", encoding="utf-8"), ensure_ascii=False)


def m_zdep(d):
    p = os.path.join(d, "proof", "A-0003.entry.json")
    raw = json.load(open(p, encoding="utf-8"))
    rec = raw[next(iter(raw))] if "body" not in raw else raw
    rec["verification"]["inclusionProof"]["hashes"][0] = flip_hex(
        rec["verification"]["inclusionProof"]["hashes"][0])
    json.dump(raw, open(p, "w", encoding="utf-8"), ensure_ascii=False)


def m_cose(d):
    p = os.path.join(d, "proof", "statement_A0003_scitt.cose")
    b = bytearray(open(p, "rb").read())
    b[-1] ^= 0x01          # 只翻签名最后一字节，结构仍合法
    open(p, "wb").write(bytes(b))


def m_pkg(d):
    """砍掉包末尾 22 字节（EOCD 记录本身）—— zipfile 因此打不开。

    早先试过"末尾多一个字节"，结果 zipfile 会向前搜索 EOCD 仍然打得开，
    破坏没生效、PKG-V032 照旧 PASS。这是**破坏手法无效**，不是检查失灵；
    换成砍 EOCD 才真正破坏包结构。
    """
    p = os.path.join(d, "proof", "pccp-bench_v0.3.2_candidate.zip")
    with open(p, "rb") as f:
        data = f.read()
    open(p, "wb").write(data[:-22])


def m_missing(d):
    os.remove(os.path.join(d, "proof", "rekor_publicKey.pem"))


def m_portable(d):
    with open(os.path.join(d, "tools", "_oops.py"), "w", encoding="utf-8") as f:
        f.write('p = r"C:\\Users\\someone\\cases.json"\n')


CASES = [
    ("M01", "v0.3 包末尾多一个字节", m_hash, "HASH-pccp-bench_v0.3_candidate.zip", ("FAIL",)),
    ("M02", "S-0001 包含路径某层哈希翻一位", m_inc, "INC-S0001", ("FAIL",)),
    ("M03", "S-0001 SET 签名翻一字节", m_set, "SET-S0001", ("FAIL",)),
    ("M04", "S-0001 checkpoint 签名翻一字节", m_cp, "CP-S0001", ("FAIL",)),
    ("M05", "S-0001 条目 logIndex 加一", m_rec, "REC-S0001", ("FAIL",)),
    ("M06", "A-0003 条目包含路径翻一位", m_zdep, "ZDEP-A0003", ("FAIL",)),
    ("M07", "COSE 签名末字节翻一位", m_cose, "SCITT-TAG18", ("FAIL",)),
    ("M08", "v0.3.2 包砍掉末尾 EOCD 记录", m_pkg, "PKG-V032", ("FAIL", "ERROR")),
    ("M09", "Rekor 公钥 PEM 被删", m_missing, "SET-S0001", ("FAIL", "ERROR")),
    ("M10", "工具里写死一条本机路径", m_portable, "PORTABLE", ("FAIL",)),
]


def main() -> int:
    if not os.path.isdir(REPO):
        print("anchors_repo 不在本机")
        return 2
    os.makedirs(OUT, exist_ok=True)

    # 0) 无破坏对照：必须 OUTSIDE_OK，否则后面所有的"检测到"都不算数
    ctl = tempfile.mkdtemp(prefix="mut_ctl_")
    d0 = os.path.join(ctl, "repo")
    shutil.copytree(REPO, d0, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    rc0, doc0 = run_outside(d0, os.path.join(ctl, "r.json"))
    ctl_ok = rc0 == 0 and doc0 and doc0.get("verdict") == "OUTSIDE_OK"
    print("对照（不做任何破坏）  %s" % ("OUTSIDE_OK" if ctl_ok else "不是 OUTSIDE_OK，后续读数无效"))
    shutil.rmtree(ctl, ignore_errors=True)

    rows = []
    for cid, desc, fn, target, expect in CASES:
        tmp = tempfile.mkdtemp(prefix="mut_")
        d = os.path.join(tmp, "repo")
        shutil.copytree(REPO, d, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        try:
            fn(d)
        except Exception as e:
            rows.append((cid, desc, target, "ERROR_ON_MUTATION", repr(e)[:80]))
            shutil.rmtree(tmp, ignore_errors=True)
            continue
        rc, doc = run_outside(d, os.path.join(tmp, "r.json"))
        status = None
        if doc:
            for c in doc.get("checks", []):
                if c["id"] == target:
                    status = c["status"]
        hit = status in expect
        rows.append((cid, desc, target, f"{status}（期望 {'/'.join(expect)}）",
                     "DETECTED" if hit else "MISSED"))
        shutil.rmtree(tmp, ignore_errors=True)

    n_hit = sum(1 for r in rows if r[4] == "DETECTED")
    print("\nMUTATION_SUITE（定向破坏 → 指定判据必须响）")
    for cid, desc, target, got, verdict in rows:
        print("  %-4s %-28s → %-14s %-22s %s" % (cid, desc, target, got, verdict))
    print("\n  检出 %d / %d" % (n_hit, len(rows)))

    ok = ctl_ok and n_hit == len(rows)
    json.dump({"generated_at": __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"),
               "label": "同操作者定向破坏（T4）：证明检查有灵敏度，不构成第三方见证",
               "control_no_mutation": "OUTSIDE_OK" if ctl_ok else "NOT_OK",
               "detected": n_hit, "total": len(rows),
               "verdict": "MUTATION_SUITE_ALL_DETECTED" if ok else "MUTATION_SUITE_HAS_MISS",
               "cases": [{"id": c[0], "desc": c[1], "target": c[2], "observed": c[3], "result": c[4]}
                         for c in rows]},
              open(os.path.join(OUT, "MUTATION_SUITE.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("\nMUTATION_SUITE_" + ("ALL_DETECTED" if ok else "HAS_MISS"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
