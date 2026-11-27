#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_v0_3_2.py —— v0.3.2：把"填了旧字段名会被静默忽略"变成"冲突就判不了"。

起因（第三十轮量化）：
  以 13 格全满为基线，只把 acceptance_criteria_met（v0.2 字段名）置 False：
    criteria_measured=True 时，v0.3 适配器用 criteria_met 覆盖同名结论
    → 输入被**静默忽略**，判决仍是 go。
  而把 v0.3 的 criteria_met 置 False：
    → reject / acceptance_not_met。

也就是说：同一个概念两个名字，填错名字不报错，只改结论。外人用 v0.2 字段名喂 v0.3 记录，
会拿到一个**看起来正常、实际错**的判决。这类"静默丢弃输入"比直接报错更危险。

v0.3.2 只改编码层（判器仍一字未动）：
  * 若 v0.2 名与 v0.3 名同时存在且结论不一致 → 该格置 None（判器视为"必填缺失"→ hold）
    并把冲突字段名写进 `_encoding_conflicts`，随判决一起返回，不藏着；
  * 只有一边存在时，按 v0.3 名优先、v0.2 名兜底；
  * 没有冲突的老用法完全不变（51 条回归必须 0 变化）。

用法：
  python build_v0_3_2.py --base-zip dist\\pccp-bench_v0.3.1_candidate.zip --out-zip dist\\pccp-bench_v0.3.2_candidate.zip
"""
import argparse
import hashlib
import json
import os
import shutil
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))

ADAPTER_V032 = '''"""Reference adapter（v0.3.2）：先展开编码，再用同一个判器。

v0.3.1 起判器从包内 snapshot 取。v0.3.2 只加一条：**冲突就判不了，不静默丢弃**。

背景（见真实回放最小编码表_20261127.md 与 corpus_replay_probe.py 的静默覆盖探针）：
  v0.3 把 acceptance 拆成 criteria_measured / criteria_met，同时保留 v0.2 的
  acceptance_criteria_met。适配器在 criteria_measured=True 时用 criteria_met 覆盖
  acceptance_criteria_met —— 也就是说，只有一边被填、另一边是旧字段名时，
  旧字段名的取值被**无声丢掉**。实测：只填 acceptance_criteria_met=False → go；
  填 criteria_met=False → reject。同名两义、填错名字不报错，最容易被外人踩。

本版做法：
  1 两边都在且不一致 → 该格置 None（判器视为必填缺失 → hold，绝不放过）；
  2 只一边在 → v0.3 名优先，v0.2 名兜底；
  3 冲突字段名写进 `_encoding_conflicts`，随判决返回，不藏。
判器字节一字未动。
"""
from __future__ import annotations

import os
import sys

PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PKG_ROOT not in sys.path:
    sys.path.insert(0, PKG_ROOT)
from snapshot.judge_pccp import JudgePccpScope  # noqa: E402

_JUDGE = JudgePccpScope()

RULE_TO_TAG = [
    ("P-CRIT-04", "not_se_to_predicate"),
    ("P-CRIT-05", "not_se_to_predicate"),
    ("P-CRIT-02", "intended_use_change"),
    ("P-CRIT-01", "no_pccp_authorized"),
    ("P-CRIT-03", "acceptance_not_met"),
    ("P-MAJ-01", "outside_scope"),
    ("P-MAJ-03", "validation_missing"),
    ("P-MAJ-05", "labeling_version_history_missing"),
    ("P-MAJ-06", "udi_not_regenerated"),
    ("P-MAJ-04", "unclassifiable"),
    ("P-MAJ-07", "evidence_missing"),
    ("L2-EVIDENCED", "evidence_missing"),
]


def expand(ctx):
    ctx = dict(ctx)
    conflicts = []

    auth = ctx.get("pccp_authorized")
    claim = ctx.get("claimed_pccp_coverage")
    actual = ctx.get("actually_within_scope")
    legacy_scope = ctx.get("change_within_pccp_scope")
    if claim is None:
        claim = legacy_scope
    if actual is None:
        actual = legacy_scope
    computed = bool(claim) and (bool(actual) or auth is False)
    if (legacy_scope is not None and claim is not None and actual is not None
            and computed != bool(legacy_scope)):
        conflicts.append("change_within_pccp_scope")
        ctx["change_within_pccp_scope"] = None
    else:
        ctx["change_within_pccp_scope"] = computed

    measured = ctx.get("criteria_measured")
    if measured is None:
        pass
    elif measured is not True:
        ctx["acceptance_criteria_met"] = None
    else:
        met = ctx.get("criteria_met")
        legacy_met = ctx.get("acceptance_criteria_met")
        if met is not None and legacy_met is not None and bool(met) != bool(legacy_met):
            conflicts.append("acceptance_criteria_met")
            ctx["acceptance_criteria_met"] = None
        else:
            ctx["acceptance_criteria_met"] = met if met is not None else legacy_met

    if conflicts:
        ctx["_encoding_conflicts"] = conflicts
    return ctx


def _tag(verdict, reasons):
    fired = [str(r.get("rule", "")) if hasattr(r, "get") else str(r) for r in reasons]
    for prefix, tag in RULE_TO_TAG:
        if any(f.startswith(prefix) for f in fired):
            return tag
    if verdict == "go":
        return "ok_covered"
    return "unclassifiable"


def evaluate(ctx):
    expanded = expand(ctx)
    conflicts = expanded.pop("_encoding_conflicts", None)
    res = _JUDGE.evaluate(expanded)
    out = {"verdict": res.get("verdict"), "tag": _tag(res.get("verdict"), res.get("reasons", [])),
           "reasons": res.get("reasons", [])}
    if conflicts:
        out["encoding_conflicts"] = conflicts
        out["conflict_policy"] = "conflicting legacy/new field names -> treated as missing -> hold"
    return out
'''

CARD = """

## v0.3.2（2026-11-27，候选，未发布）—— 冲突不再静默

量化事实：v0.3 适配器在 `criteria_measured=True` 时用 `criteria_met` 覆盖
`acceptance_criteria_met`。于是只填旧字段名 `acceptance_criteria_met=False` → 判决 **go**；
填新字段名 `criteria_met=False` → **reject / acceptance_not_met**。同一个概念两个名字，
填错名字不报错、只改结论。

v0.3.2 只改编码层（判器一字未动）：两边都在且不一致 → 该格置 None（判器按"必填缺失"给 hold），
冲突字段名随判决返回（`encoding_conflicts`）。没有冲突的老用法完全不变。
"""


def sha256_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-zip", required=True)
    ap.add_argument("--out-zip", required=True)
    a = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="pccp_v032_")
    with zipfile.ZipFile(a.base_zip) as z:
        z.extractall(tmp)
    dd = os.path.join(tmp, "dataset")

    open(os.path.join(dd, "adapter_reference.py"), "w", encoding="utf-8").write(ADAPTER_V032)
    with open(os.path.join(dd, "DATASET_CARD.md"), "a", encoding="utf-8") as f:
        f.write(CARD)

    # MANIFEST 重算（与 v0.3.1 同一规则）
    files = []
    for root, _d, fs in os.walk(tmp):
        for fn in fs:
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, tmp).replace("\\", "/")
            if rel == "MANIFEST.json":
                continue
            files.append({"path": rel, "sha256": sha256_file(full), "bytes": os.path.getsize(full)})
    nodes = [bytes.fromhex(f["sha256"]) for f in sorted(files, key=lambda x: x["path"])]
    while len(nodes) > 1:
        if len(nodes) % 2:
            nodes.append(nodes[-1])
        nodes = [hashlib.sha256(nodes[i] + nodes[i + 1]).digest() for i in range(0, len(nodes), 2)]
    man = json.load(open(os.path.join(tmp, "MANIFEST.json"), encoding="utf-8"))
    man["version"] = "0.3.2"
    man["files"] = files
    man["leaf_count"] = len(files)
    man["bytes"] = sum(f["bytes"] for f in files)
    man["merkle_root"] = nodes[0].hex() if nodes else ""
    man["adapter_note"] = "v0.3.2: conflicting legacy/new field names are treated as missing (hold)"
    json.dump(man, open(os.path.join(tmp, "MANIFEST.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    os.makedirs(os.path.dirname(os.path.abspath(a.out_zip)), exist_ok=True)
    with zipfile.ZipFile(a.out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _d, fs in os.walk(tmp):
            for fn in fs:
                full = os.path.join(root, fn)
                z.write(full, os.path.relpath(full, tmp).replace("\\", "/"))

    print("out        ", a.out_zip, os.path.getsize(a.out_zip), "bytes")
    print("sha256     ", sha256_file(a.out_zip))
    print("manifest   leaf_count", man["leaf_count"], "bytes", man["bytes"], "merkle", man["merkle_root"][:16])
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
