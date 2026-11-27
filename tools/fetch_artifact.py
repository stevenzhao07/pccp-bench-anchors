#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch_artifact.py —— 取回工作流产物（绕开 401）。

GitHub 的 artifacts/zip 会 302 到 Azure Blob；第二跳若还带 Authorization 头，
会报 InvalidAuthenticationInfo(401)。做法：第一跳带 token，拿到 Location 后
第二跳不带任何认证头直接取。
"""
import argparse
import io
import json
import os
import sys
import urllib.request
import zipfile


def get(url, token=None):
    r = urllib.request.Request(url, headers={"User-Agent": "pccp-anchor-fetch",
                                             "Accept": "application/vnd.github+json"})
    if token:
        r.add_header("Authorization", "Bearer " + token)
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    try:
        return opener.open(r, timeout=90), None
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308):
            return None, e.headers.get("Location")
        raise


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="stevenzhao07/pccp-bench-anchors")
    ap.add_argument("--run-id", type=int, required=True)
    ap.add_argument("--out", required=True, help="sigstore 回条保存路径")
    ap.add_argument("--info", default="out/anchor_A0003.json")
    a = ap.parse_args()

    token = os.environ["GH_TOKEN"]
    resp, _ = get("https://api.github.com/repos/%s/actions/runs/%s/artifacts" % (a.repo, a.run_id), token)
    arts = json.loads(resp.read().decode())
    art = arts["artifacts"][0]

    resp, loc = get("https://api.github.com/repos/%s/actions/artifacts/%s/zip" % (a.repo, art["id"]), token)
    if loc is None:
        blob = resp.read()
    else:
        resp2, _ = get(loc)          # 第二跳不带 token
        blob = resp2.read()

    z = zipfile.ZipFile(io.BytesIO(blob))
    names = z.namelist()
    bundle = [n for n in names if n.endswith(".sigstore.json") or n.endswith(".sigstore")]
    info = {"artifact_id": art["id"], "artifact_name": art["name"], "files": names}
    if bundle:
        b = json.loads(z.read(bundle[0]))
        open(a.out, "wb").write(z.read(bundle[0]))
        tlog = (b.get("verificationMaterial", {}).get("tlogEntries") or [{}])[0]
        info.update({"bundle_file": bundle[0], "logIndex": tlog.get("logIndex"),
                     "logId": (tlog.get("logId") or {}).get("keyId"),
                     "integratedTime": tlog.get("integratedTime"),
                     "treeSize": (tlog.get("inclusionProof") or {}).get("treeSize")})
    json.dump(info, open(a.info, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(info, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
