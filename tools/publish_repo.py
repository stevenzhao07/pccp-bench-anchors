#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""publish_repo.py —— 用 git-data API 写仓（本机 github.com 不通，只有 api.github.com 通）。

token 从环境变量 GH_TOKEN 读，不打印、不落盘。
用法：python publish_repo.py --repo owner/name --branch main --message "..." path1=local1 path2=local2
"""
import argparse
import base64
import json
import os
import time
import urllib.error
import urllib.request

API = "https://api.github.com"


def req(method, path, token, payload=None):
    url = API + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    r = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "User-Agent": "pccp-anchors-publisher",
        "Content-Type": "application/json",
    })
    for attempt in range(4):
        try:
            with urllib.request.urlopen(r, timeout=90) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body.strip() else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8")[:300]
            raise SystemExit("%s %s -> %s %s" % (method, path, e.code, detail))
        except Exception:
            if attempt == 3:
                raise
            time.sleep(3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--branch", default="main")
    ap.add_argument("--message", required=True)
    ap.add_argument("pairs", nargs="+")
    a = ap.parse_args()

    token = os.environ.get("GH_TOKEN", "")
    if not token.startswith("gh") and len(token) < 20:
        raise SystemExit("GH_TOKEN missing")

    ref = req("GET", "/repos/%s/git/ref/heads/%s" % (a.repo, a.branch), token)
    head = ref["object"]["sha"]
    base_tree = req("GET", "/repos/%s/git/commits/%s" % (a.repo, head), token)["tree"]["sha"]

    entries = []
    for pair in a.pairs:
        repo_path, local = pair.split("=", 1)
        raw = open(local, "rb").read()
        blob = req("POST", "/repos/%s/git/blobs" % a.repo, token,
                   {"content": base64.b64encode(raw).decode("ascii"), "encoding": "base64"})
        entries.append({"path": repo_path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        print("blob", repo_path, blob["sha"][:12], len(raw), "bytes")

    tree = req("POST", "/repos/%s/git/trees" % a.repo, token,
               {"base_tree": base_tree, "tree": entries})
    commit = req("POST", "/repos/%s/git/commits" % a.repo, token,
                 {"message": a.message, "tree": tree["sha"], "parents": [head]})
    req("PATCH", "/repos/%s/git/refs/heads/%s" % (a.repo, a.branch), token,
        {"sha": commit["sha"], "force": False})
    print("commit", commit["sha"])
    print("tree  ", tree["sha"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
