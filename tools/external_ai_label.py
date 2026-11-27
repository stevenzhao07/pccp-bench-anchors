#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""external_ai_label.py —— 让外部模型盲判 51 条（只给事实与判据说明，不给标签）。

用途：打破"作者自己给自己打分"的闭环。外部模型与本判器、与本标签表均无关系，
只能拿题面事实 + R1 判据说明作判断，因此它的输出是一个可对照的第三列。

凭据：key 只在内存里读、只用不打印；文件路径可用 --key-file 覆盖。
"""
import argparse
import json
import os
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_KEY_FILE = r"<ai-key-file>"
ENDPOINT = "https://api.siliconflow.cn/v1/chat/completions"
MODEL = "deepseek-ai/DeepSeek-V3"

SYSTEM = """You are an independent regulatory reviewer for US FDA PCCP (predetermined change control plan)
scope questions under FD&C Act §515C and 21 CFR 892.2055. You receive one case at a time as JSON
facts. Decide exactly one verdict and exactly one tag.

VERDICTS
  go     — the change may be implemented now under an authorized PCCP: it stays inside the authorized
           scope, the modification class is described, the acceptance criteria were measured and met,
           verification/validation is documented, labeling carries the version history, a new UDI was
           generated, intended use is unchanged, and the device remains substantially equivalent.
  hold   — the change cannot be cleared on today's record, but the gap is remediable by adding
           evidence or paperwork (missing V&V, missing version history, missing UDI, undescribed class,
           outside the authorized scope so a new submission must be assessed, authorization status
           unstated, evidence insufficient). Stop and complete the record.
  reject — the change cannot ride this PCCP at all and no amount of paperwork fixes it: intended use
           or a fundamental claim moves; substantial equivalence to the predicate is broken; the
           modified version is used as the predicate; the firm claims PCCP coverage but no authorized
           PCCP exists; measured acceptance criteria were NOT met.

TAGS (choose one, exactly this spelling)
  ok_covered | outside_scope | acceptance_not_met | evidence_missing | intended_use_change | unclassifiable
Use unclassifiable only when the facts cannot be placed in any of the other five.

RULES OF THOUGHT
  - Decide remediability, not severity: a missing document is hold, a measured failure is reject.
  - Absent is not met: an unmeasured criterion is hold, never go.
  - A proposal or an industry practice is not a current requirement.
  - Copying the wording of the plan does not prove the criterion was satisfied.

Output STRICT JSON only, no prose, one object per case:
{"verdict":"go|hold|reject","tag":"...","why":"<=12 words"}"""

USER_TMPL = """Cases (JSON array). For each element decide verdict and tag per the rules.

%s

Return a JSON array of objects, one per case, each with keys: case_id, verdict, tag, why."""


def load_key(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        raw = f.read()
    for tok in raw.replace("\n", " ").split():
        t = tok.strip().strip('",')
        if t.startswith("sk-") and len(t) > 20:
            return t
    raise SystemExit("no sk- token found in key file")


def call(key, cases):
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": USER_TMPL % json.dumps(cases, ensure_ascii=False, indent=1)},
        ],
        "temperature": 0.0,
        "max_tokens": 2000,
    }
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


FACT_KEYS = ["case_id", "device_description", "pccp_authorized", "change_within_pccp_scope",
             "affects_intended_use", "change_class_described", "acceptance_criteria_met",
             "validation_documented", "labeling_version_history", "udi_updated",
             "remains_se_to_predicate", "evidence_sufficiency", "change_type"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=os.path.join(HERE, "out", "cases_public_v0_2b.json"))
    ap.add_argument("--key-file", default=DEFAULT_KEY_FILE)
    ap.add_argument("--batch", type=int, default=6)
    ap.add_argument("--out", default=os.path.join(HERE, "out", "external_ai_labels.json"))
    a = ap.parse_args()

    key = load_key(a.key_file)
    cases = json.load(open(a.cases, encoding="utf-8"))
    cases = cases.get("cases", cases)
    facts = [{k: c.get(k) for k in FACT_KEYS if k in c} for c in cases]

    got = []
    for i in range(0, len(facts), a.batch):
        chunk = facts[i:i + a.batch]
        for attempt in range(3):
            try:
                raw = call(key, chunk)
                break
            except Exception as exc:
                print("batch %d attempt %d failed: %s" % (i, attempt + 1, type(exc).__name__))
                time.sleep(4)
        else:
            raise SystemExit("batch %d failed after 3 attempts" % i)
        s = raw[raw.index("["):raw.rindex("]") + 1]
        got.extend(json.loads(s))
        print("batch %d-%d ok" % (i, i + len(chunk) - 1))
        time.sleep(1)

    json.dump(got, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("labelled", len(got), "->", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
