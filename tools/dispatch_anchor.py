#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dispatch_anchor.py —— 触发 keyless-anchor 工作流，等它跑完，取回回条关键读数。

只走 api.github.com（本机 github.com 不通）。token 从 GH_TOKEN 读，不打印。
"""
import argparse
import io
import json
import os
import time
import urllib.error
import urllib.request
import zipfile

API = "https://api.github.com"


def req(method, path, token, payload=None, raw=False):
    url = API + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    r = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "User-Agent": "pccp-anchor-dispatch",
        "Content-Type": "application/json",
    })
    for attempt in range(4):
        try:
            with urllib.request.urlopen(r, timeout=90) as resp:
                body = resp.read()
                return body if raw else (json.loads(body.decode("utf-8")) if body.strip() else {})
        except urllib.error.HTTPError as e:
            raise SystemExit("%s %s -> %s %s" % (method, path, e.code, e.read().decode()[:300]))
        except Exception:
            if attempt == 3:
                raise
            time.sleep(3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="stevenzhao07/pccp-bench-anchors")
    ap.add_argument("--workflow", default="keyless-anchor.yml")
    ap.add_argument("--path", required=True)
    ap.add_argument("--sha", required=True)
    ap.add_argument("--out", default="out/anchor_A0003.json")
    ap.add_argument("--timeout", type=int, default=600)
    a = ap.parse_args()

    token = os.environ.get("GH_TOKEN", "")
    if len(token) < 20:
        raise SystemExit("GH_TOKEN missing")

    req("POST", "/repos/%s/actions/workflows/%s/dispatches" % (a.repo, a.workflow), token,
        {"ref": "main", "inputs": {"artifact_path": a.path, "artifact_url": "",
                                   "expect_sha256": a.sha}})

    run = None
    t0 = time.time()
    while time.time() - t0 < a.timeout:
        time.sleep(8)
        runs = req("GET", "/repos/%s/actions/runs?event=workflow_dispatch&per_page=5" % a.repo, token)
        for r in runs.get("workflow_runs", []):
            if r["path"].endswith(a.workflow) and r["head_sha"] == runs["workflow_runs"][0]["head_sha"]:
                run = r
                break
        if run and run["status"] == "completed":
            break
        run = None
    if not run:
        raise SystemExit("no completed run within timeout")

    info = {"run_id": run["id"], "conclusion": run["conclusion"], "head_sha": run["head_sha"],
            "created_at": run["created_at"], "html_url": run["html_url"]}

    arts = req("GET", "/repos/%s/actions/runs/%s/artifacts" % (a.repo, run["id"]), token)
    if not arts.get("artifacts"):
        info["bundle"] = None
        json.dump(info, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(json.dumps(info, ensure_ascii=False, indent=1))
        return 0

    art = arts["artifacts"][0]
    info["artifact_id"] = art["id"]
    blob = req("GET", "/repos/%s/actions/artifacts/%s/zip" % (a.repo, art["id"]), token, raw=True)
    z = zipfile.ZipFile(io.BytesIO(blob))
    bundle_name = [n for n in z.namelist() if n.endswith(".sigstore.json") or n.endswith(".sigstore")]
    if bundle_name:
        b = json.loads(z.read(bundle_name[0]))
        tlog = (b.get("verificationMaterial", {}).get("tlogEntries") or [{}])[0]
        info["bundle_file"] = bundle_name[0]
        info["logIndex"] = tlog.get("logIndex")
        info["logId"] = (tlog.get("logId") or {}).get("keyId")
        info["kindVersion"] = tlog.get("kindVersion")
        info["integratedTime"] = tlog.get("integratedTime")
    with open(os.path.basename(a.out) + ".bundle.sigstore.json", "wb") as f:
        f.write(z.read(bundle_name[0]))
    json.dump(info, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(info, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
