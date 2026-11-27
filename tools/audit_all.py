#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_all.py —— 一条命令，把本项目对外说过的每一句"可复算"重新从字节算一遍。

设计原则：
1. 只读。不联网的检查默认全跑；联网/三方依赖的检查用 --with-network 才跑。
2. 每项检查都有明确的判据（哈希相等 / 脚本返回 0 / 负例必须被拒），不是"跑通了"。
3. 输出两层：out/STATE_OF_UNION.json（机器读）+ out/STATE_OF_UNION.md（人读）。
4. 把**做不到的事**也写进同一份输出（gaps 段），不让它们靠"没提"蒙过去。

用法：
    python audit_all.py                  # 离线全量
    python audit_all.py --with-network   # 追加联网探活 + sigstore 官方交叉验
退出码：0 = 所有非 SKIP 检查通过；1 = 有 FAIL/ERROR。
"""
import argparse
import hashlib
import io
import json
import os
import platform
import re
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
DIST = os.path.join(HERE, "dist")
ANCHORS = os.path.join(HERE, "anchors_repo")

# ---- 台账硬读数（来自公共日志的字节，不是自述） ----
SHA = {
    "A-0001": "1907e93a21305c3055777dda2f3c85f037501d821bba08abb37f7ac8127aaf61",
    "A-0002": "b19fd9d6dc473fee5f069449ef71541f28be9d455074336bb85db4db7fd349bd",
    "A-0003": "d684eaca7b2ba32483c23a1474815bf0314dd2cdf8770648eb7b6e2c1826ed99",
    "S-0001-payload": "bda911e8d9a794b67f62684bb64420ff6a6cd978eb8230905cd049e2280bc9d4",
}
LOGINDEX = {"S-0001": 4145697630, "A-0003": 4143787841}
FILES = {
    "A-0001": os.path.join(OUT, "anchor_A0001_artifact.bin"),
    "A-0002": os.path.join(OUT, "receipt_demo5.canonical.json"),
    "A-0003": os.path.join(DIST, "pccp-bench_v0.3_candidate.zip"),
}

results = []


def add(cid, group, claim, status, detail, kind="offline"):
    results.append({"id": cid, "group": group, "claim": claim, "status": status,
                    "detail": str(detail)[:600], "kind": kind})


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(args, cwd=HERE, timeout=180):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable] + args, cwd=cwd, capture_output=True,
                       text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, env=env)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def tail(txt, n=3):
    lines = [l for l in txt.strip().splitlines() if l.strip()]
    return " | ".join(lines[-n:])[:400]


# ---------------- 1. 字节哈希 ----------------
def check_hashes():
    for aid, expect in SHA.items():
        if aid == "S-0001-payload":
            continue
        path = FILES[aid]
        try:
            got = sha256_file(path)
            add("HASH-" + aid, "bytes", f"{aid} 的产物字节哈希等于台账登记值",
                "PASS" if got == expect else "FAIL",
                f"sha256={got[:16]}… 期望 {expect[:16]}… size={os.path.getsize(path)}")
        except Exception as e:
            add("HASH-" + aid, "bytes", f"{aid} 的产物字节哈希", "ERROR", repr(e))


# ---------------- 2. S-0001 明细字段 ----------------
def check_s0001_record():
    """从公共日志返回体本身取字段，核对与我们台账写的一致。"""
    try:
        raw = json.load(open(os.path.join(OUT, "rekor_statement_entry_only.json"), encoding="utf-8"))
        uuid = next(iter(raw))
        rec = raw[uuid]
        body = json.loads(__import__("base64").b64decode(rec["body"]))
        h = body["spec"]["data"]["hash"]
        idx = rec["logIndex"]
        ok = (h["value"] == SHA["S-0001-payload"] and h["algorithm"] == "sha256"
              and idx == LOGINDEX["S-0001"] and body.get("kind") == "hashedrekord")
        add("REC-S0001", "anchor", "S-0001 在公共日志条目里的 hash 值与 logIndex 与台账一致",
            "PASS" if ok else "FAIL",
            f"kind={body.get('kind')} alg={h['algorithm']} logIndex={idx} sha={h['value'][:16]}…")
    except Exception as e:
        add("REC-S0001", "anchor", "S-0001 条目字段", "ERROR", repr(e))


# ---------------- 3. 三项公证判据（离线） ----------------
def check_rekor_primitives():
    entry = os.path.join("out", "rekor_statement_entry_only.json")
    key = os.path.join("out", "rekor_publicKey.json")
    for cid, script, extra, note in [
        ("INC-S0001", "verify_rekor_inclusion.py", ["--entry", entry], "Merkle 包含路径"),
        ("SET-S0001", "verify_set.py", ["--entry", entry, "--public-key", key], "签名条目时间戳(SET)"),
        ("CP-S0001", "verify_anchor.py", ["--entry", entry, "--public-key", key], "checkpoint 签名"),
    ]:
        rc, txt = run([script] + extra)
        add(cid, "anchor", f"{note}能被离线重算并校验通过", "PASS" if rc == 0 else "FAIL", tail(txt))


# ---------------- 4. 零依赖六项 ----------------
def check_zero_dep():
    rc, txt = run(["verify_zero_dep.py",
                   "--bundle", os.path.join("out", "anchor_A0003.bundle.sigstore.json"),
                   "--artifact", os.path.join("dist", "pccp-bench_v0.3_candidate.zip"),
                   "--entry", os.path.join("out", "anchor_entry_A0003.json"),
                   "--rekor-key", os.path.join("out", "rekor_publicKey.json"),
                   "--intermediate", os.path.join("out", "fulcio_intermediate.pem"),
                   "--root", os.path.join("out", "fulcio_root.pem")])
    ok = rc == 0 and "ZERO_DEP_ALL_PASS" in txt
    rows = [l.strip() for l in txt.splitlines() if re.match(r"\s+[A-Z_]+\s+(OK|FAIL)", l)]
    add("ZDEP-A0003", "anchor", "A-0003 的六项（绑定/LOGID/包含/checkpoint/SET/证书链）零三方依赖全过",
        "PASS" if ok else "FAIL", f"{len(rows)} 行判据；" + " | ".join(rows))


# ---------------- 5. SCITT 陈述：带标签/不带标签/篡改 ----------------
def check_scitt():
    pub = os.path.join("out", "scitt_test_pub.pem")
    art = os.path.join("dist", "pccp-bench_v0.3_candidate.zip")
    for cid, f, want in [("SCITT-TAG18", "statement_A0003_scitt.cose", "tag 18"),
                         ("SCITT-UNTAGGED", "statement_A0003.cose", "untagged")]:
        rc, txt = run(["verify_scitt_statement.py",
                       "--statement", os.path.join("out", f),
                       "--pubkey-pem", pub, "--artifact", art])
        ok = rc == 0 and "SCITT_ALL_PASS" in txt and want in txt and "BINDING        OK" in txt
        add(cid, "scitt", f"COSE_Sign1 陈述（{want}）验签通过，且 subject_sha256 与包字节绑定",
            "PASS" if ok else "FAIL", tail(txt, 4))
    rc, txt = run(["verify_scitt_statement.py",
                   "--statement", os.path.join("out", "statement_A0003_scitt.cose"),
                   "--pubkey-pem", pub, "--tamper"])
    add("SCITT-TAMPER", "scitt", "篡改一个字节后必须验不过（证明不是恒真）",
        "PASS" if rc != 0 and "SCITT_HAS_FAIL" in txt else "FAIL", tail(txt, 2))


# ---------------- 6. 包内自测 ----------------
def check_pkg_selfcheck():
    kit = os.path.join(OUT, "pkg_v032_kit", "dataset")
    rc, txt = run(["selfcheck.py"], cwd=kit)
    ok = rc == 0 and "SELFCHECK_ALL_PASS" in txt and "51/51" in txt
    add("PKG-V032", "package", "v0.3.2 包在空目录自跑 51/51 判决一致，cases_sha256 与登记一致",
        "PASS" if ok else "FAIL", tail(txt, 3))


# ---------------- 7. κ 自检 ----------------
def check_kappa():
    rc, txt = run(["kappa.py", "--selftest"])
    ok = rc == 0 and "KAPPA_SELFTEST_ALL_PASS" in txt
    add("KAPPA", "agreement", "κ 计算器的四个解析算例（0.4 / 1.0 / 0.0 / 0.798）全部对上",
        "PASS" if ok else "FAIL", tail(txt, 4))


# ---------------- 8. 盲标包：结构性证明"包里没答案" ----------------
def check_blind_kit():
    """结构性证明：包里拿到答案的唯一途径被堵死了。

    判据只有四条，都是可机械复核的：
      1) 成员名里不出现 key/answer 文件；
      2) 10 题表的"判决"列逐行为空（表头里的 go/hold/reject 是选项提示，属正常，不算泄漏）；
      3) 答案键里的内部标注串（tag / kind / provenance）在包内任何文件里都不出现；
      4) 题量与约定一致（10 题），回填模板同为 10 行且判决列为空。
    """
    kit = os.path.join(DIST, "pccp-t1-blind-kit_20261127.zip")
    try:
        key = json.load(open(os.path.join(OUT, "blind_kit_key.json"), encoding="utf-8"))
    except Exception as e:
        add("BLIND-NOANSWER", "t1", "盲标包内不含答案", "ERROR", repr(e))
        return

    marks = set()
    for cid, v in key.items():
        if isinstance(v, dict):
            # 只用 tag / provenance 这类"本项目内部标注串"当哨兵；
            # kind 的取值（described / boundary）会与题面字段名 change_class_described 撞词，不能当哨兵。
            for k in ("tag", "provenance"):
                if isinstance(v.get(k), str) and len(v[k]) >= 4:
                    marks.add(v[k])

    problems = []
    with zipfile.ZipFile(kit) as z:
        names = z.namelist()
        if any(("key" in n.lower() or "answer" in n.lower()) for n in names):
            problems.append("成员名里出现 key/answer")
        for n in names:
            blob = z.read(n).decode("utf-8", "replace")
            for m in marks:
                if m in blob:
                    problems.append(f"{n} 命中内部标注串 {m}")
        # 逐行核判决列是否为空
        blind = [n for n in names if n.endswith("cases_blind_10.csv")]
        rater = [n for n in names if n.endswith("rater_verdicts.csv")]
        if not blind:
            problems.append("缺 cases_blind_10.csv")
        else:
            import csv
            rows = list(csv.reader(io.StringIO(z.read(blind[0]).decode("utf-8-sig"))))
            header = rows[0]
            col = [i for i, h in enumerate(header) if "判决" in h]
            body = [r for r in rows[1:] if any(x.strip() for x in r)]
            if len(body) != 10:
                problems.append(f"题目 {len(body)} 行（应为 10）")
            if not col:
                problems.append("找不到判决列")
            else:
                filled = [r[0] for r in body if len(r) > col[0] and r[col[0]].strip()]
                if filled:
                    problems.append(f"{len(filled)} 行判决列已预填答案")
        if not rater:
            problems.append("缺 rater_verdicts.csv 回填模板")
        else:
            import csv
            rr = list(csv.reader(io.StringIO(z.read(rater[0]).decode("utf-8-sig"))))
            rh, rb = rr[0], [r for r in rr[1:] if any(x.strip() for x in r)]
            if len(rb) != 10:
                problems.append(f"回填模板 {len(rb)} 行（应为 10）")
            vc = [i for i, h in enumerate(rh) if "verdict" in h.lower() or "判决" in h]
            if vc and any(len(r) > vc[0] and r[vc[0]].strip() for r in rb):
                problems.append("回填模板已带预设判决")
    add("BLIND-NOANSWER", "t1",
        "10 题盲标包结构上不含答案（无答案文件、判决列全空、内部标注串零出现）",
        "PASS" if not problems else "FAIL",
        "成员 %d 个；%s" % (len(names), "; ".join(problems) or "无泄漏"))


# ---------------- 9.5 外人视角：把仓拷到临时目录，只用仓内字节验 ----------------
def check_outside():
    rc, txt = run(["outside_check.py"], timeout=300)
    ok = rc == 0 and "OUTSIDE_OK" in txt
    add("OUTSIDE", "outside",
        "把 anchors_repo 拷到临时目录后，只用仓内 tools/ proof/ certs/ 就能验完 12 项",
        "PASS" if ok else "FAIL", tail(txt, 3))
    rc2, txt2 = run(["outside_check.py", "--selftest"], timeout=120)
    ok2 = rc2 == 0 and "PORTABLE_SELFTEST_OK" in txt2
    add("OUTSIDE-SELFTEST", "outside",
        "可移植性扫描的非空性：种入一条本机路径后必须被抓到（否则该检查是摆设）",
        "PASS" if ok2 else "FAIL", tail(txt2, 2))


# ---------------- 9.6 定向破坏：每一项判据都要能被改坏触发 ----------------
def check_mutations():
    rc, txt = run(["mutate_check.py"], timeout=900)
    ok = rc == 0 and "MUTATION_SUITE_ALL_DETECTED" in txt
    add("MUTATION", "sensitivity",
        "十处定向破坏（哈希/包含/SET/checkpoint/条目/六项/签名/包/公钥/路径）各自都能让指定判据失败",
        "PASS" if ok else "FAIL", tail(txt, 2))


# ---------------- 9. 口径机审 ----------------
def check_claims():
    if not os.path.isdir(ANCHORS):
        add("CLAIMS", "claims", "文档禁语机审", "SKIP", "anchors_repo 不在本机")
        return
    rc, txt = run(["claim_audit.py", "--paths", "anchors_repo"])
    ok = rc == 0 and "CLAIM_AUDIT_CLEAN" in txt
    add("CLAIMS", "claims", "全部 markdown 已过禁语机审（禁语只活在否定语境）",
        "PASS" if ok else "FAIL", tail(txt, 3))


# ---------------- 10. 联网 / 三方依赖（可选） ----------------
def check_network():
    rc, txt = run(["check_interop_links.py"], timeout=240)
    add("LINKS", "interop", "18 个上下游/互补目标链接可探活（三态 LIVE/AUTH/DEAD/UNKNOWN）",
        "PASS" if rc == 0 else "FAIL", tail(txt, 3), kind="network")
    rc, txt = run(["verify_with_sigstore.py"], timeout=240)
    ok = rc == 0 and "SIGSTORE_OFFICIAL_VERIFY_OK" in txt
    add("SIGSTORE", "interop", "sigstore 官方库用其自带信任根重算 S-0001 四项判据通过",
        "PASS" if ok else "FAIL", tail(txt, 3), kind="third-party")


# ---------------- 11. 做不到的事（同一份输出里写清） ----------------
def collect_gaps():
    gaps = []
    ret_dir = os.path.join(HERE, "t1_pack", "returns")
    n_ret = len([f for f in os.listdir(ret_dir)]) if os.path.isdir(ret_dir) else 0
    gaps.append({"item": "T1 第三方实测", "count": n_ret,
                 "status": "0 件" if n_ret == 0 else f"{n_ret} 件",
                 "note": "盲标包已就绪，缺一位与项目无关的评审人；发送需用户指定渠道"})
    try:
        dry = json.load(open(os.path.join(OUT, "blind_dryrun.json"), encoding="utf-8"))
        gaps.append({"item": "κ 真实读数", "count": 0, "status": "仅干跑",
                     "note": "A：%s；B：%s；口径=%s" % (
                         dry.get("a_vs_label", "-"), dry.get("b_vs_label", "-"),
                         dry.get("label", "-"))})
    except Exception:
        gaps.append({"item": "κ 真实读数", "count": 0, "status": "仅干跑", "note": "读数文件缺失"})
    v032 = "v0.3.2"
    anchored = False
    try:
        txt = open(os.path.join(ANCHORS, "ANCHORS.md"), encoding="utf-8").read()
        anchored = bool(re.search(r"v0\.3\.2[^\n]{0,80}logIndex", txt))
    except Exception:
        pass
    gaps.append({"item": "A-0004 锚定 v0.3.2", "count": 0,
                 "status": "已锚" if anchored else "未锚", "note": "等一个字；候选包已在 dist/"})
    gaps.append({"item": "真实 PCCP 变更回放", "count": 0, "status": "0 条",
                 "note": "缺'人 + 14 格 + 每格可直达引用'的真实变更档案"})
    gaps.append({"item": "已投递 issue 的回复", "count": 0, "status": "0 回复",
                 "note": "三处 201 Created（croissant #1078 / py-scrapi #10 / scrapi-wg #215）"})
    return gaps


# ---------------- 输出 ----------------
def summarise():
    n = {"PASS": 0, "FAIL": 0, "ERROR": 0, "SKIP": 0}
    for r in results:
        n[r["status"]] = n.get(r["status"], 0) + 1
    return n


def write_outputs():
    s = summarise()
    ok = s["FAIL"] == 0 and s["ERROR"] == 0
    doc = {
        "generated_at": __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"),
        "env": {"platform": platform.platform(), "python": sys.version.split()[0],
                "host": platform.node()},
        "verdict": "ALL_CHECKS_PASS" if ok else "HAS_FAILURE",
        "summary": s,
        "checks": results,
        "gaps": collect_gaps(),
        "claim_boundary": [
            "本输出证明的是：这些字节、这些哈希、这些签名关系能被任何人在离线环境重算一致。",
            "本输出不证明：判据内容在监管意义上正确、第三方已见证、或本项目优于任何他人实现。",
        ],
    }
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "STATE_OF_UNION.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)

    lines = ["# 收尾总账（由 audit_all.py 自动生成）", "",
             f"生成时间：{doc['generated_at']}　环境：{doc['env']['platform']} / Python {doc['env']['python']}",
             "", f"**判定：{doc['verdict']}**　通过 {s['PASS']} / 失败 {s['FAIL']} / 出错 {s['ERROR']} / 跳过 {s['SKIP']}", "",
             "## 逐项检查", "", "| # | 检查 | 判据 | 结果 | 读数 |", "|---|---|---|---|---|"]
    for i, r in enumerate(results, 1):
        lines.append("| %d | `%s` | %s | %s | %s |" % (
            i, r["id"], r["claim"], r["status"], r["detail"].replace("|", "／")[:180]))
    lines += ["", "## 仍未做到的（同一份总账里列清）", "", "| 事项 | 现状 | 说明 |", "|---|---|---|"]
    for g in doc["gaps"]:
        lines.append("| %s | %s | %s |" % (g["item"], g["status"], g["note"]))
    lines += ["", "## 口径边界", ""] + ["- " + c for c in doc["claim_boundary"]]
    with open(os.path.join(OUT, "STATE_OF_UNION.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return ok, s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-network", action="store_true", help="追加联网探活与三方依赖交叉验")
    a = ap.parse_args()

    check_hashes()
    check_s0001_record()
    check_rekor_primitives()
    check_zero_dep()
    check_scitt()
    check_pkg_selfcheck()
    check_kappa()
    check_blind_kit()
    check_outside()
    check_mutations()
    check_claims()
    if a.with_network:
        check_network()
    else:
        add("LINKS", "interop", "上下游链接探活", "SKIP", "未加 --with-network")
        add("SIGSTORE", "interop", "sigstore 官方库交叉验", "SKIP", "未加 --with-network")

    ok, s = write_outputs()
    print("STATE_OF_UNION")
    for r in results:
        print("  %-16s %-6s %s" % (r["id"], r["status"], r["detail"][:110]))
    print("\n  summary: PASS=%d FAIL=%d ERROR=%d SKIP=%d" % (s["PASS"], s["FAIL"], s["ERROR"], s["SKIP"]))
    print("  ->" , os.path.join("out", "STATE_OF_UNION.json"))
    print("\nSTATE_OF_UNION_" + ("ALL_PASS" if ok else "HAS_FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
