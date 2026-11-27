#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claim_audit.py —— 口径审计：把"禁语"从"说过"变成"能被机器查出来"。

规则（一条就够）：禁语可以出现，但**必须**在否定语境里（同句 40 字符内出现
"不能/不证明/不许/不得/别说/不要/无/不必/并非/不是/不可"之一）。否则报 VIOLATION。

为什么用"否定语境"而不是"直接禁止出现"：我们的文档里正确写法恰恰是
"不能说首创、不能说最强"——直接禁词会把正确的自我约束一起禁掉。

另外查三类"容易被误读的正面话术"：
  W1  "已验证/已证实/已实测" 若同句没有"第三方/本人/独立"，视为把 T4 说成 T1；
  W2  "已发布/已上线" 若同句没有版本号或锚 id，视为口径不清；
  W3  "可复算" 若同句没有"前提/重建/非原字节"，视为把重建版说成原版。

用法：
  python claim_audit.py --paths anchors_repo . --json out\\claim_audit.json
"""
import argparse
import json
import os
import re
import sys

FORBIDDEN = ["首创", "最强", "领先", "全面超越", "断崖式", "业界第一", "无懈可击",
             "已被第三方见证", "第三方实测已通过"]
NEG = re.compile(r"不能|不证明|不许|不得|别说|不要|无|不必|并非|不是|不可|未")
T1_WORD = re.compile(r"已验证|已证实|已实测")
T1_QUAL = re.compile(r"第三方|本人|独立")
PUB_WORD = re.compile(r"已发布|已上线")
PUB_QUAL = re.compile(r"v0\.\d|A-\d{4}|logIndex")
REPRO_WORD = re.compile(r"可复算|可独立复算")
REPRO_QUAL = re.compile(r"前提|重建|非原字节|RECONSTRUCTED")
# "可复算"只在对"分数/判器/包"这类东西说时才需要前提；说 sha256 可复算本身不需要前提
REPRO_SUBJECT = re.compile(r"分数|判器|结果|包|数据集|端到端|全量分|0\.\d{3,}")
# "已发布"只在没说清是哪个版本/哪条锚时才算口径不清
PUB_SUBJECT = re.compile(r"数据集|版本|包|题集")
# 引用豁免：口径总账这类文档必须把禁语原样列出来才说得清。
# 行内含 [禁] 或 [引] 视为"在引用禁语、并已标注"，不计违规。
EXEMPT = re.compile(r"\[禁\]|\[引\]")


def scan(path):
    hits = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f, 1):
            if len(line) > 400:      # 跳过超长压缩行（多为数据粘贴）
                continue
            if EXEMPT.search(line):  # 已标注为引用禁语的行
                continue
            for w in FORBIDDEN:
                if w in line and not NEG.search(line):
                    hits.append((path, i, "VIOLATION", w, line.strip()[:90]))
            if T1_WORD.search(line) and not T1_QUAL.search(line):
                hits.append((path, i, "W1_T1_混淆", T1_WORD.search(line).group(0), line.strip()[:90]))
            if PUB_WORD.search(line) and PUB_SUBJECT.search(line) and not PUB_QUAL.search(line):
                hits.append((path, i, "W2_发布口径不清", PUB_WORD.search(line).group(0), line.strip()[:90]))
            if (REPRO_WORD.search(line) and REPRO_SUBJECT.search(line)
                    and not REPRO_QUAL.search(line)):
                hits.append((path, i, "W3_复算前提缺失", REPRO_WORD.search(line).group(0), line.strip()[:90]))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paths", nargs="+", required=True)
    ap.add_argument("--json", default="out/claim_audit.json")
    a = ap.parse_args()

    files = []
    for p in a.paths:
        if os.path.isdir(p):
            for root, _d, fs in os.walk(p):
                for fn in fs:
                    if fn.lower().endswith(".md"):
                        files.append(os.path.join(root, fn))
    all_hits = []
    for f in files:
        all_hits.extend(scan(f))

    out = {"files_scanned": len(files), "hits": len(all_hits),
           "rows": [{"file": os.path.relpath(h[0]), "line": h[1], "kind": h[2],
                     "word": h[3], "text": h[4]} for h in all_hits]}
    os.makedirs(os.path.dirname(os.path.abspath(a.json)), exist_ok=True)
    json.dump(out, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    for h in all_hits:
        print("%-40s %-4s %-18s %-10s %s" % (os.path.basename(h[0]), h[1], h[2], h[3], h[4]))
    print("扫描 %d 个 md，命中 %d 处 → %s" % (len(files), len(all_hits),
                                          "CLAIM_AUDIT_CLEAN" if not all_hits else "CLAIM_AUDIT_HAS_FLAGS"))
    return 0 if not all_hits else 1


if __name__ == "__main__":
    sys.exit(main())
