# ANCHORS.md —— 锚定台账

只记事实：锚定了什么字节、由哪条工作流、落在日志哪一条。**不做结论、不写评价。**

## S-0001 · 2026-11-27（陈述锚 / A4 的 RFC 9162 一侧）

用户明确批准（"发"）后写入公共 Rekor。**与 A-000x 不同**：A-000x 锚的是包字节，
S-0001 锚的是一条 COSE 陈述的 payload 摘要 + 我们对 payload 的签名（hashedrekord 形状）。

| 项 | 值 |
|---|---|
| 陈述 | `interop/statement_A0003_scitt.cose`（654 B；payload 390 B） |
| payload sha256 | `bda911e8d9a794b67f62684bb64420ff6a6cd978eb8230905cd049e2280bc9d4` |
| Rekor uuid | `108e9186e8c5677a81303f8666057bac63cda4dafa8dff89babbb250562b032b5f296823112f3486` |
| logIndex | **4145697630**（integratedTime 1795770765） |
| logID | `c0d23d6ad406973f9559f3ba2d1ca01f84147d8ffc5b8445c224f98b9591801d` |
| 包含性证明 | root `8533948bb1266c3b6b98f6374f79d338c2c84811da3b69c6b3bc49414a4626c1`，depth 22 → **OK** |
| checkpoint 签名 | **OK**（keyhash `c0d23d6a`） |
| SET 签名 | **OK** |
| 绑定 | 条目 digest == payload sha256 → **OK**；条目公钥对 payload 验签名 → **OK** |
| 对面一侧 | CCF 模式 SCITT 模拟器：`entryId 1`，回执 `interop/emu_receipt.cbor`，leaf `e5b9b98d…` / root `a1097320…` |

口径：两侧**不是同一字节被同时受理**——A 侧绑陈述字节，B 侧绑 payload 摘要与签名，由 payload sha256 相连。
详见 `A4双服务_20261127.md`。

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

## A-0002 · 2026-11-27

锚定对象：跑分回执的**规范化字节**（不是磁盘上那份带缩进的 JSON——两者字节不同、哈希也不同，见下方"为什么"）。

| 项 | 值 |
|---|---|
| 产物 | `receipts/receipt_demo5.canonical.json`（761 B） |
| sha256 | `b19fd9d6dc473fee5f069449ef71541f28be9d455074336bb85db4db7fd349bd` |
| 签名身份 | `.../pccp-bench-anchors/.github/workflows/keyless-anchor.yml@refs/heads/main` |
| issuer | `https://token.actions.githubusercontent.com` |
| 工作流运行 | run 45944158703（commit `9131d586`） |
| Rekor 条目 uuid | `108e9186e8c5677a5d766b5be83229d51a5c3e60eba51e7db014ec5685a97bd4ffeece2051989e56` |
| Rekor logIndex | 4142064557（integratedTime 1795756228） |
| 包含性 / checkpoint / SET | **OK / OK / OK**（treeSize 4,020,185,771） |
| 绑定 | bundle digest == 条目 digest == 规范字节 sha256 → **OK** |
| 身份匹配 | issuer + SAN URI → **OK** |

**为什么锚规范化字节**：`receipt_self_sha256` 是对"去掉该字段后按键排序、紧凑分隔符"的字节算的，
不是对磁盘文件算的。签磁盘那份（缩进版，sha256 `8ce767e1…`）会与自述哈希对不上——
签出来的是一个"看起来像回执、但绑定链对不上"的物件。这类坑必须以文件字节为准去签。

**与 A-0000 的关系**：同一哈希 `b19fd9d6…` 现在有**两条公共记录**——
A-0000（自生成密钥，uuid `108e9186…e16285`）与 A-0002（工作流身份）。
前者只证明"某哈希进过日志、某时刻存在"，后者证明"这份字节由该工作流产出"。**两条并存，谁也不是谁的替代。**

## A-0000 · 2026-11-26（本台账建立前的历史条目）

用**自生成密钥**写入公共 Rekor 的真回执条目，作为"先跑通链路"的物证保留，不冒充身份签名。

| 项 | 值 |
|---|---|
| 产物 | 回执规范化字节，sha256 `b19fd9d6…49bd` |
| 条目 uuid | `108e9186e8c5677adc28aadf6661c67a212f370292a95a628353be53c1db6742334c2e13d6e16285` |
| 写入方式 | `POST /api/v1/log/entries` → 201（hashedrekord，自签密钥） |
| 校验（事后复算） | 包含性 OK / checkpoint OK / SET OK / 绑定 OK |
| **没有的东西** | 公钥无身份绑定 → **不证明"是谁写的"** |

## A-0003 · 2026-11-27（v0.3 候选包）

| 项 | 值 |
|---|---|
| 产物 | `dist/pccp-bench_v0.3_candidate.zip`（拆标志 + 11 字词表 + 包内 v0.3 适配器；判器字节未改） |
| 字节数 | 69,421 B |
| sha256 | `d684eaca7b2ba32483c23a1474815bf0314dd2cdf8770648eb7b6e2c1826ed99` |
| 签名身份（SAN URI） | `https://github.com/stevenzhao07/pccp-bench-anchors/.github/workflows/keyless-anchor.yml@refs/heads/main` |
| OIDC issuer | `https://token.actions.githubusercontent.com` |
| 工作流运行 | run 45956271779（workflow_dispatch，commit `7f4f4148`，artifacts id 15179071601） |
| Rekor 条目 uuid | `108e9186e8c5677af6e6345f2d538805c61ef77b81a04c74990026eef923431269f4fee8e08258a4` |
| Rekor logIndex | 4143787841（integratedTime 1795763247） |
| 包含性证明 | treeSize 4,021,883,613 / proof.logIndex 4,021,883,579 → **OK**（depth 26） |
| checkpoint 签名 | **OK**（body+LF） |
| SET 签名 | **OK**（sorted-compact） |
| 证书链 | leaf←intermediate←root 全 **OK**（零第三方依赖工具验出） |
| 绑定 | bundle digest == 条目 hashedrekord digest == 产物 sha256 → **OK** |
| 身份匹配 | issuer + SAN URI 双项匹配 → **OK** |

验算（零依赖，只需 Python 3.9+）：

```bash
curl -sSL 'https://raw.githubusercontent.com/stevenzhao07/pccp-bench-anchors/main/tools/verify_zero_dep.py' -o vz.py
curl -s 'https://rekor.sigstore.dev/api/v1/log/entries?logIndex=4143787841' -o entry.json
python vz.py --entry entry.json --rekor-key rekor_publicKey.json \
  --intermediate certs/fulcio_intermediate.pem --root certs/fulcio_root.pem
# 期望 ZERO_DEP_ALL_PASS
```

## 口径（A-0003 新增）

- A-0003 锚的是**候选包**字节，不等于"已发布数据集"：hidden 承诺未换、Zenodo 未更新、README 未改口径。
- 包内 51 条公开题得分 51/51 是**作者把标签与判器对齐后的天花板**，不是独立验证；
  同一批题由外部模型（未给标签）盲判 50/51，唯一分歧 `P240006` 因 `change_type` 缺字段。
- 判器字节（`snapshot/judge_pccp.py`）与 A-0001/A-0002 时期完全相同，一字未改。
