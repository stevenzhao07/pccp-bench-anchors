#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""measure_verify_cost.py —— 把"零依赖"从口号变成读数。

对同一份 S-0001 条目，量三件事：
  1) 我方三个验算器：代码行数、第三方依赖数、能否离线、耗时
  2) sigstore 官方实现：传递依赖数、磁盘占用、能否离线、耗时（已由 verify_with_sigstore.py 读出 1.1 ms）
  3) 结论只能写"差多少"，不能写"更好"——两种方案各有代价，速度在我们这边确实是劣势。
"""
from __future__ import annotations

import importlib.metadata as md
import json
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(".")


def loc(p: str) -> tuple[int, int]:
    s = pathlib.Path(p).read_text(encoding="utf-8", errors="replace").splitlines()
    code = [l for l in s if l.strip() and not l.strip().startswith("#")]
    return len(s), len(code)


def third_party_imports(p: str) -> list[str]:
    """粗算：抓顶层 import 名，剔掉标准库与本项目自建模块。"""
    import ast
    try:
        tree = ast.parse(pathlib.Path(p).read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return ["(parse error)"]
    std = set(sys.stdlib_module_names)
    names = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                names.add(a.name.split(".")[0])
        elif isinstance(n, ast.ImportFrom):
            if n.level == 0 and n.module:
                names.add(n.module.split(".")[0])
    local = {q.stem for q in HERE.glob("*.py")} | {"enc", "p256", "util", "common"}
    return sorted(n for n in names if n not in std and n not in local)


def dist_size(name: str) -> int:
    try:
        d = md.distribution(name)
    except md.PackageNotFoundError:
        return 0
    total = 0
    for f in (d.files or []):
        try:
            total += (d.locate_file(f)).stat().st_size
        except OSError:
            pass
    return total


def transitive(roots: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    stack = list(roots)
    while stack:
        n = stack.pop()
        key = n.lower().replace("_", "-")
        if key in seen:
            continue
        try:
            d = md.distribution(n)
        except md.PackageNotFoundError:
            continue
        seen[key] = 1
        for r in (d.requires or []):
            if "extra ==" in r:      # 只算运行时依赖，剔 dev/doc/lint extras
                continue
            base = r.split(";")[0].split("[")[0]
            for sep in ("==", ">=", "<=", "~=", "!=", ">", "<", " "):
                base = base.split(sep)[0]
            base = base.strip()
            if base:
                stack.append(base)
    return sorted(seen)


def main() -> int:
    ours = ["verify_rekor_inclusion.py", "verify_set.py", "verify_anchor.py",
            "verify_zero_dep.py"]
    report = {"ours": {}, "sigstore": {}}

    for f in ours:
        if not pathlib.Path(f).exists():
            continue
        raw, code = loc(f)
        report["ours"][f] = {"lines": raw, "code_lines": code,
                             "third_party": third_party_imports(f)}

    # 我方耗时：只量 anchor（最重的那个：note 验签 + P-256）
    t0 = time.perf_counter()
    r = subprocess.run([sys.executable, "verify_anchor.py",
                        "--entry", "out/rekor_statement_entry_only.json",
                        "--public-key", "out/rekor_publicKey.json"],
                       capture_output=True, text=True)
    ms = (time.perf_counter() - t0) * 1e3
    report["ours"]["verify_anchor.py"]["runtime_ms_incl_startup"] = round(ms, 1)
    report["ours"]["verify_anchor.py"]["exit"] = r.returncode
    report["ours"]["verify_anchor.py"]["tail"] = (r.stdout or r.stderr).strip().splitlines()[-2:]

    # sigstore 侧
    roots = ["sigstore"]
    deps = transitive(roots)
    total = sum(dist_size(d) for d in deps)
    report["sigstore"] = {
        "direct_requires": len([r for r in (md.requires("sigstore") or []) if ";" not in r or "extra" not in r]),
        "transitive_dists_installed": len(deps),
        "dists": deps,
        "disk_mb": round(total / 1e6, 1),
        "runtime_ms_full_verify": None,
    }
    cc = json.load(open("out/sigstore_crosscheck.json", encoding="utf-8"))
    report["sigstore"]["runtime_ms_full_verify"] = cc["positive"]["full(_verify)"]["ms"]
    report["sigstore"]["verdict"] = cc["verdict"]

    json.dump(report, open("out/verify_cost.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print("== 我方 ==")
    for f, v in report["ours"].items():
        if "lines" in v:
            print("  %-28s 行 %4d / 代码 %4d | 三方依赖 %s"
                  % (f, v["lines"], v["code_lines"], v["third_party"] or "0"))
    a = report["ours"].get("verify_anchor.py", {})
    print("  verify_anchor.py 端到端（含解释器启动）: %.1f ms, exit=%s"
          % (a.get("runtime_ms_incl_startup", -1), a.get("exit")))
    print("== sigstore 官方 ==")
    print("  直接依赖 %d 条 / 实装传递包 %d 个 / 磁盘 %.1f MB"
          % (report["sigstore"]["direct_requires"],
             report["sigstore"]["transitive_dists_installed"],
             report["sigstore"]["disk_mb"]))
    print("  全量 verify 耗时: %s ms（不含进程启动）" % report["sigstore"]["runtime_ms_full_verify"])
    print("  判据结果: %s" % report["sigstore"]["verdict"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
