#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""post_issues.py —— 把两份缺陷报告作为 issue 发到对应仓库。

为什么单独写：issue 是**对外不可撤回**的动作，所以先落盘草稿（issue_draft_*.md），
再由这个脚本一次性发、并打印 issue 号与 URL 存档，便于事后核对"发出去的到底是什么"。
"""
from __future__ import annotations

import json
import os
import sys

import httpx

TOKEN = os.environ.get("GH_TOKEN", "")
API = "https://api.github.com"

ISSUES = [
    {
        "repo": "scitt-community/scitt-api-emulator",
        "title": "decode() rejects any tagged COSE_Sign1 when cbor2>=6 (CBORTag.value is a tuple); install also blocked by unpublished rkvst-archivist",
        "file": "issue_draft_emulator.md",
    },
    {
        "repo": "mlcommons/croissant",
        "title": "Validator requires @type https://schema.org/FileObject where Croissant examples use cr:FileObject",
        "file": "issue_draft_croissant.md",
    },
]


def main() -> int:
    if not TOKEN:
        print("GH_TOKEN 缺失")
        return 1
    h = {"Authorization": "Bearer " + TOKEN, "Accept": "application/vnd.github+json",
         "X-GitHub-Api-Version": "2022-11-28"}
    out = []
    for it in ISSUES:
        body = open(it["file"], encoding="utf-8").read()
        r = httpx.post("%s/repos/%s/issues" % (API, it["repo"]),
                       headers=h, json={"title": it["title"], "body": body}, timeout=60)
        print("%-40s %s" % (it["repo"], r.status_code))
        if r.status_code == 201:
            j = r.json()
            print("   #%s %s" % (j["number"], j["html_url"]))
            out.append({"repo": it["repo"], "number": j["number"], "url": j["html_url"],
                        "title": j["title"], "created_at": j["created_at"]})
        else:
            print("   ", r.text[:300])
    json.dump(out, open("out/issues_published.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return 0 if len(out) == len(ISSUES) else 1


if __name__ == "__main__":
    sys.exit(main())
