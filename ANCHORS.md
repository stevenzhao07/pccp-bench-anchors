# ANCHORS.md —— 锚定台账

只记事实：锚定了什么字节、由哪条工作流、落在日志哪一条。**不做结论、不写评价。**

## A-0001 · 2026-11-27

| 项 | 值 |
|---|---|
| 产物 | `pccp-bench_zenodo_v0.1.0.zip`（PCCP-bench 数据集 v0.1.0） |
| 字节数 | 60,505 B |
| sha256 | `1907e93a21305c3055777dda2f3c85f037501d821bba08abb37f7ac8127aaf61` |
| 签名身份（SAN URI） | `https://github.com/stevenzhao07/pccp-bench-anchors/.github/workflows/keyless-anchor.yml@refs/heads/main` |
| OIDC issuer | `https://token.actions.githubusercontent.com` |
| 工作流运行 | run 45939667784（workflow_dispatch，commit `1c5c06a3`） |
| Rekor 条目 uuid | `108e9186e8c5677af843593161340828b40bb18932471e29f78b866e3273ef425f48e8357cff2d17` |
| Rekor logIndex | 4141390895（integratedTime 1795753439） |
| 包含性证明 | treeSize 4,020,058,879 / proof.logIndex 4,019,486,633 → **OK** |
| checkpoint 签名 | **OK**（keyhash `c0d23d6a`） |
| SET 签名 | **OK**（canonicalization `sorted-compact`） |
| 绑定 | bundle digest == 条目 hashedrekord digest == 产物 sha256 → **OK** |
| 身份匹配 | issuer + SAN URI 双项匹配 → **OK** |

验算命令（任何人可复跑）：

```bash
# 取回条目
curl -s 'https://rekor.sigstore.dev/api/v1/log/entries?logIndex=4141390895' | jq .
# 验 bundle（装 cosign 的情况）
cosign verify-blob --bundle artifact.bin.sigstore.json \
  --certificate-identity-regexp 'https://github.com/stevenzhao07/pccp-bench-anchors/.github/workflows/keyless-anchor.yml@.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  artifact.bin
```

## 口径

- `proof.logIndex` 与条目自身 `logIndex` 不一致（4,019,486,633 vs 4,141,390,895）是公共实例 API 语义：
  证明按较新树快照计算。**以绑定为准，不拿 index 当唯一标识。**
- 锚定证明"这份字节由这条工作流在该时刻产出"。**不证明内容正确**，不证明评测结论成立。
- 构建产物保留 90 天后过期；Rekor 条目不会消失。
