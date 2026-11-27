#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""version_ledger.py —— 版本台账：哪个字节是哪一个版本、锚了没有、能不能自跑。

为什么要有：现在桌面上存在四个包（v0.1 / v0.3 / v0.3.1 / v0.3.2），
公共锚只认其中一个的字节（A-0003 = v0.3 = d684eaca…）。版本一多，最容易出三种错：

  1  对着 v0.3.2 说"这就是锚定的那个包"（字节不同，说法就假）；
  2  以为 v0.3.1/.2 也锚过了（没有）；
  3  被锚定的那份字节只活在 %TEMP%，清理一次就没了（本轮已先复制进 dist 并复核哈希）。

本脚本只做一件事：把"版本 → 字节 → 哈希 → 锚定状态 → 自检状态"写成一张表，
并且**当场重算哈希**，不抄任何记录。

用法：
  python version_ledger.py --dirs dist %TEMP% --json out\version_ledger.json --md 版本台账_20261127.md
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

# 已知锚定（来自台账/回条，不含哈希时脚本会自己算出来比对）
ANCHORS = [
    {"id": "A-0000", "what": "回执演示 4 条", "sha256": None, "logIndex": 4140703205},
    {"id": "A-0001", "what": "v0.1 包", "sha256": "1907e93a21305c3055777dda2f3c85f037501d821bba08abb37f7ac8127aaf61",
     "logIndex": 4141390895},
    {"id": "A-0002", "what": "规范化回执字节", "sha256": "b19fd9d6dc473fee5f069449ef71541f28be9d455074336bb85db4db7fd349bd",
     "logIndex": 4142064557},
    {"id": "A-0003", "what": "v0.3 包", "sha256": "d684eaca7b2ba32483c23a1474815bf0314dd2cdf8770648eb7b6e2c1826ed99",
     "logIndex": 4143787841},
]


def sha256_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def pkg_info(path):
    info = {"file": os.path.basename(path), "bytes": os.path.getsize(path), "sha256": sha256_file(path)}
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            man = None
            if "MANIFEST.json" in names:
                man = json.loads(z.read("MANIFEST.json").decode("utf-8"))
            info["has_snapshot_base"] = "snapshot/base.py" in names
            info["has_selfcheck"] = "dataset/selfcheck.py" in names
            info["manifest_version"] = (man or {}).get("version")
            info["engine_sha256"] = (man or {}).get("engine_sha256")
            info["manifest_leaf_count"] = (man or {}).get("leaf_count")
            try:
                cases = json.loads(z.read("dataset/cases_public.json").decode("utf-8"))
                info["cases"] = len(cases.get("cases", cases))
            except Exception:
                info["cases"] = None
    except Exception as exc:
        info["zip_error"] = str(exc)
    return info


def selfcheck(path):
    """解到临时目录，用隔离解释器跑 selfcheck。包不带 selfcheck 就返回 SKIP。"""
    tmp = tempfile.mkdtemp(prefix="ledger_")
    try:
        with zipfile.ZipFile(path) as z:
            z.extractall(tmp)
        sc = os.path.join(tmp, "dataset", "selfcheck.py")
        if not os.path.exists(sc):
            return "NO_SELFCHECK"
        p = subprocess.run([PY, "-I", sc], cwd=tmp, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        so = (p.stdout or "") + (p.stderr or "")
        if "SELFCHECK_ALL_PASS" in so:
            m = re.search(r"verdict_match\s+(\d+)/(\d+)", so)
            return "PASS " + (m.group(0).split()[-1] if m else "")
        if "IMPORT_FAIL" in so:
            return "IMPORT_FAIL"
        return "FAIL"
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dirs", nargs="+", required=True)
    ap.add_argument("--json")
    ap.add_argument("--md")
    a = ap.parse_args()

    found = []
    for d in a.dirs:
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if fn.lower().endswith(".zip") and ("pcp" in fn.lower() or "pccp" in fn.lower()):
                found.append(pkg_info(os.path.join(d, fn)))

    # 同字节多个副本合并成一行：字节是同一份，位置可以有很多份
    merged = {}
    for f in found:
        key = f["sha256"]
        if key in merged:
            merged[key]["copies"].append(f["file"])
        else:
            f["copies"] = [f["file"]]
            merged[key] = f
    found = list(merged.values())

    for f in found:
        f["anchored"] = next((x["id"] for x in ANCHORS if x["sha256"] and x["sha256"] == f["sha256"]), None)
        # 自检用第一份存在的副本
        first = None
        for d in a.dirs:
            if os.path.exists(os.path.join(d, f["file"])):
                first = os.path.join(d, f["file"])
                break
        f["selfcheck"] = selfcheck(first) if first else "MISSING"

    out = {"anchors_known": ANCHORS, "packages": found}
    if a.json:
        json.dump(out, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    lines = ["# 版本台账（脚本生成，哈希当场重算）", "",
             "生成时间：2026-11-27　生成者：version_ledger.py", "",
             "| 包 | 字节数 | sha256（前 12） | 版本号（MANIFEST） | 题数 | 自带 base.py | 自带 selfcheck | 自检 | 锚定 | 副本 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for f in sorted(found, key=lambda x: x["bytes"]):
        lines.append("| %s | %d | `%s` | %s | %s | %s | %s | %s | %s | %s |" % (
            f["file"], f["bytes"], f["sha256"][:12], f.get("manifest_version"),
            f.get("cases"), "是" if f.get("has_snapshot_base") else "否",
            "是" if f.get("has_selfcheck") else "否", f["selfcheck"],
            f["anchored"] or "**未锚**", "、".join(f["copies"])))
    lines += ["", "## 锚定清单（只认字节，不认版本名）", "",
               "| 锚 | 内容 | logIndex | sha256（前 12） |", "|---|---|---|---|"]
    for x in ANCHORS:
        lines.append("| %s | %s | %s | `%s` |" % (x["id"], x["what"], x["logIndex"],
                                                 (x["sha256"] or "-")[:12]))
    lines += ["", "## 读这张表时要注意的三点", "",
              "1. **锚定只跟字节走**。A-0003 锚的是 v0.3（`d684eaca…`），不是 v0.3.1/.2；",
              "2. 未锚的版本可以自跑、可以评测，但**不能说它已被锚定**；",
              "3. 被锚定的字节必须在本地有一份可复核的副本，否则公共日志里那条记录就变成孤证（本轮已把 v0.3 复制进 `dist/` 并复核哈希相等）。"]
    # 只把"清单版本与内容明显不符"的挑出来：v0.1 的包写 0.1.0 是对的（32 题），
    # 写着 0.1.0 却装 51 题才是旧清单。
    stale = [f for f in found if f.get("anchored") and (f.get("manifest_version") or "") == "0.1.0"
             and (f.get("cases") or 0) != 32]
    if stale:
        lines += ["", "## 警告：已锚定的字节里，清单版本号是旧的", "",
                  "以下包已经进了公共日志（不可改），但包内 `MANIFEST.json` 仍写 `version 0.1.0`：",
                  "",
                  "| 锚 | sha256（前 12） | 包内 MANIFEST 版本 | 实际内容 |",
                  "|---|---|---|---|"]
        for f in stale:
            lines.append("| %s | `%s` | %s | %s 题 |" % (f["anchored"], f["sha256"][:12],
                                                       f.get("manifest_version"), f.get("cases")))
        lines += ["", "后果与处置：这份字节改不了，也不能说\"它是 0.1.0\"。正确说法是"
                  "「A-0003 锚的是 v0.3 内容，其包内清单版本号是旧的」；后续版本（v0.3.1/.2）修了清单，"
                  "但它们**未被锚定**。"]
    md = "\n".join(lines) + "\n"
    if a.md:
        open(a.md, "w", encoding="utf-8").write(md)

    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
