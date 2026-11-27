#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_v0_3_1.py —— v0.3.1：把"包看起来能跑"变成"包真的能跑"。

起因（第二十八轮）：把 v0.3 候选包解到一个**干净空目录**、用 `python -I`（不继承环境路径）
导入，两条致命错：

  1   dataset/adapter_reference.py 写的是 from lgd_engine.judges.judge_pccp import ...
      —— 包里没有 lgd_engine 这个目录；
  2   snapshot/judge_pccp.py 里是 from .base import ... ，而包里既没有 snapshot/base.py，
      也没有 snapshot/__init__.py。

于是"外人拿到包就能自己算出 51/51"这句话，在包被解开的那一刻就是假的：外人一跑必报
ModuleNotFoundError。此前所有 51/51 的读数，都是在**我们自己的引擎树**里跑的（lgd_engine 在）。

本版修什么（只修包装，不动判器字节、不动题面标签）：
  A  snapshot/__init__.py + snapshot/base.py 打进包（base.py 取重建版，含 RECONSTRUCTED 标注）
  B  adapter 改成 from snapshot.judge_pccp import JudgePccpScope，路径以包根为准
  C  新增 dataset/selfcheck.py：无依赖、无网络，跑完直接打印"判决一致 n/N、标签率、case sha"
  D  MANIFEST.json / dataset_manifest.json 按**实际内容**重算（原 MANIFEST 还挂着 v0.1 的
     leaf_count=14、engine sha 是 v0.1 判器 —— 也就是清单与内容不同源）
  E  DATASET_CARD 追加 v0.3.1 段，把上面两个错写在卡上，不写在脚注

判器字节不变：本版仍要求 snapshot/judge_pccp.py 的 sha 等于 v0.3 里的那个
（7ee356ea...e3dd 是 v0.1 引擎；v0.3 的判器 sha 在建包时实测打印，见输出）。

用法：
  python build_v0_3_1.py --base-zip "%TEMP%\\pcp_bench_v0_3_candidate.zip" --out-zip dist\\pccp-bench_v0.3.1_candidate.zip
"""
import argparse
import hashlib
import json
import os
import shutil
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_PY_SRC = os.path.join(HERE, "repro", "lgd_engine", "judges", "base.py")

ADAPTER_V031 = '''"""Reference adapter（v0.3.1）：先展开编码，再用同一个判器。

与 v0.3 的差别只有一行：判器从包内 snapshot 取，不再假设本机存在 lgd_engine。
（v0.3 的写法在外人机器上必然 ModuleNotFoundError，见 DATASET_CARD 的 v0.3.1 段。）

展开式（四种组合逐一验过，见 v03编码层修复_20261127.md）：
  change_within_pccp_scope = claimed AND (actual OR NOT authorized)
  acceptance_criteria_met  = None 若未按类型测；否则 = met

标签优先级 = R1 语义（可补救 → hold，不可补救 → reject），11 字词表。
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
    auth = ctx.get("pccp_authorized")
    claim = ctx.get("claimed_pccp_coverage")
    actual = ctx.get("actually_within_scope")
    if claim is None:
        claim = ctx.get("change_within_pccp_scope")
    if actual is None:
        actual = ctx.get("change_within_pccp_scope")
    ctx["change_within_pccp_scope"] = bool(claim) and (bool(actual) or auth is False)

    measured = ctx.get("criteria_measured")
    if measured is None:
        pass
    elif measured is not True:
        ctx["acceptance_criteria_met"] = None
    else:
        ctx["acceptance_criteria_met"] = ctx.get("criteria_met")
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
    res = _JUDGE.evaluate(expand(ctx))
    verdict = res.get("verdict")
    return {"verdict": verdict, "tag": _tag(verdict, res.get("reasons", [])),
            "reasons": res.get("reasons", [])}
'''

SELFCHECK = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selfcheck.py —— 不给网络、不给环境变量，跑完就知道这包能不能用。

它只回答三件事：
  1  包里的判器 + 包里的适配器能不能 import（不能就报 IMPORT_FAIL，退出码 2）
  2  51 条上判决与标签是否一致（不一致就把 case_id 列出来）
  3  题集本身的 sha256（别人拿到同一份包，sha 必须一样）

用法（在包根目录）：
  python dataset/selfcheck.py
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(HERE)
sys.path.insert(0, PKG_ROOT)
sys.path.insert(0, HERE)

CASES = os.path.join(HERE, "cases_public.json")


def main() -> int:
    raw = open(CASES, "rb").read()
    print("cases_sha256   " + hashlib.sha256(raw).hexdigest())
    doc = json.loads(raw.decode("utf-8"))
    cases = doc.get("cases", doc)

    try:
        import adapter_reference as adapter
    except Exception as exc:
        print("IMPORT_FAIL    " + type(exc).__name__ + ": " + str(exc))
        return 2

    verdict_ok = tag_ok = 0
    misses = []
    tag_misses = []
    for c in cases:
        ctx = {k: v for k, v in c.items() if not k.startswith("expected_")}
        res = adapter.evaluate(ctx)
        if res.get("verdict") == c.get("expected_verdict"):
            verdict_ok += 1
        else:
            misses.append((c["case_id"], res.get("verdict"), c.get("expected_verdict")))
        if res.get("tag") == c.get("expected_tag"):
            tag_ok += 1
        else:
            tag_misses.append((c["case_id"], res.get("tag"), c.get("expected_tag")))

    n = len(cases)
    print("verdict_match  %d/%d" % (verdict_ok, n))
    print("tag_rate       %.4f" % (tag_ok / n))
    for m in misses:
        print("  MISS  %s  got=%s  want=%s" % m)
    for m in tag_misses[:10]:
        print("  TAG   %s  got=%s  want=%s" % m)
    overall = "SELFCHECK_ALL_PASS" if verdict_ok == n and tag_ok == n else "SELFCHECK_HAS_FAIL"
    print(overall)
    return 0 if overall == "SELFCHECK_ALL_PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
'''

CARD_V031 = """

## v0.3.1（2026-11-27，候选，未发布）—— 修"包不能自跑"

把 v0.3 包解到**空目录**、用隔离解释器导入，两条致命错当场暴露：

1. `dataset/adapter_reference.py` 写的是 `from lgd_engine.judges.judge_pccp import ...`，
   包里没有 `lgd_engine`；
2. `snapshot/judge_pccp.py` 是 `from .base import ...`，包里既没有 `snapshot/base.py`，
   也没有 `snapshot/__init__.py`。

结论：**v0.3 包对外人不可运行**。此前所有"51/51、标签率 1.0"的读数，都是在作者自己的引擎树里
跑出来的（那儿有 `lgd_engine`）。这不是数据错，是包装错，但后果一样——外人一跑就
ModuleNotFoundError。

本版修（判器字节一字未动）：
- 打进 `snapshot/__init__.py` 与 `snapshot/base.py`（base 取**重建版**，文件内带
  RECONSTRUCTED 标注：其中 `is_unusable` / `misused` 是按判器唯一调用点重建的，
  **不是**作者原字节）；
- adapter 改为 `from snapshot.judge_pccp import JudgePccpScope`，路径以包根为准；
- 新增 `dataset/selfcheck.py`：无依赖、无网络，一条命令输出判决一致数 / 标签率 / 题集 sha；
- `MANIFEST.json`、`dataset/dataset_manifest.json` 按实际内容重算（原 MANIFEST 还挂着
  v0.1 的 `leaf_count=14` 与 v0.1 判器 sha —— 清单与内容不同源，属同类缺陷）。

仍然不是：不是发布版；隐藏题不随包发；没有真实变更回放；`base.py` 不是作者原字节。
"""


def sha256_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def merkle(files):
    """MANIFEST 里写死的规则：leaf = 文件 sha256 的字节；按 path 排序；pairwise sha256(a+b)；奇数与自身配对。"""
    nodes = [bytes.fromhex(f["sha256"]) for f in sorted(files, key=lambda x: x["path"])]
    if not nodes:
        return ""
    while len(nodes) > 1:
        if len(nodes) % 2:
            nodes.append(nodes[-1])
        nodes = [hashlib.sha256(nodes[i] + nodes[i + 1]).digest() for i in range(0, len(nodes), 2)]
    return nodes[0].hex()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-zip", required=True)
    ap.add_argument("--out-zip", required=True)
    a = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="pccp_v031_")
    with zipfile.ZipFile(a.base_zip) as z:
        z.extractall(tmp)

    snap = os.path.join(tmp, "snapshot")
    dd = os.path.join(tmp, "dataset")

    # A 打进 snapshot 包体
    open(os.path.join(snap, "__init__.py"), "w", encoding="utf-8").write("")
    shutil.copyfile(BASE_PY_SRC, os.path.join(snap, "base.py"))

    # B 换 adapter
    open(os.path.join(dd, "adapter_reference.py"), "w", encoding="utf-8").write(ADAPTER_V031)

    # C 自检脚本
    open(os.path.join(dd, "selfcheck.py"), "w", encoding="utf-8").write(SELFCHECK)

    # E 卡上写清
    with open(os.path.join(dd, "DATASET_CARD.md"), "a", encoding="utf-8") as f:
        f.write(CARD_V031)

    # D MANIFEST 重算（不含 MANIFEST 自身）
    files = []
    for root, _dirs, fs in os.walk(tmp):
        for fn in fs:
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, tmp).replace("\\", "/")
            if rel == "MANIFEST.json":
                continue
            files.append({"path": rel, "sha256": sha256_file(full), "bytes": os.path.getsize(full)})
    total = sum(f["bytes"] for f in files)
    man = {
        "dataset": "PCCP-Bench",
        "version": "0.3.1",
        "frozen_at_utc": "2026-11-27T00:00:00Z",
        "leaf_count": len(files),
        "bytes": total,
        "engine_sha256": sha256_file(os.path.join(snap, "judge_pccp.py")),
        "engine_base_sha256": sha256_file(os.path.join(snap, "base.py")),
        "engine_base_is_original": False,
        "merkle_root": merkle(files),
        "merkle_rule": "leaf = the file's sha256 digest bytes (not re-hashed with the path), files sorted by 'path'; pairwise sha256(a+b); an odd node pairs with itself",
        "files": files,
    }
    json.dump(man, open(os.path.join(tmp, "MANIFEST.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # dataset_manifest 按实际题集重算
    cases = json.load(open(os.path.join(dd, "cases_public.json"), encoding="utf-8"))
    cases = cases.get("cases", cases)
    mix, tags, prov = {}, {}, {}
    for c in cases:
        mix[c["expected_verdict"]] = mix.get(c["expected_verdict"], 0) + 1
        tags[c["expected_tag"]] = tags.get(c["expected_tag"], 0) + 1
        p = c.get("label_provenance", "unknown")
        prov[p] = prov.get(p, 0) + 1
    dm = {
        "version": "v0.3.1",
        "when": "2026-11-27",
        "total": len(cases),
        "public": len(cases),
        "hidden": 10,
        "hidden_note": "10 条隐藏题不随包发布，承诺在 hidden_commitment.json",
        "by_verdict": mix,
        "by_tag": tags,
        "by_label_provenance": prov,
        "cases_sha256": sha256_file(os.path.join(dd, "cases_public.json")),
        "baseline_always_go": round(max(mix.values()) / len(cases), 4),
    }
    json.dump(dm, open(os.path.join(dd, "dataset_manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # 打包
    outdir = os.path.dirname(os.path.abspath(a.out_zip))
    os.makedirs(outdir, exist_ok=True)
    with zipfile.ZipFile(a.out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, fs in os.walk(tmp):
            for fn in fs:
                full = os.path.join(root, fn)
                z.write(full, os.path.relpath(full, tmp).replace("\\", "/"))

    print("out        ", a.out_zip, os.path.getsize(a.out_zip), "bytes")
    print("sha256     ", sha256_file(a.out_zip))
    print("engine_sha ", man["engine_sha256"])
    print("cases      ", len(cases), "mix:", mix, "baseline:", dm["baseline_always_go"])
    print("manifest   leaf_count", man["leaf_count"], "bytes", total, "merkle", man["merkle_root"][:16])
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
