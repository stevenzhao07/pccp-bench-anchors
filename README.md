# pccp-bench-anchors

PCCP-bench 产物的**锚定记录仓**。每次锚定由本仓的一条 GitHub Actions 工作流完成：

1. 取回指定产物（默认 PCCP-bench v0.1.0 数据集 zip）
2. 校验 sha256（与期望值不符则直接失败，不产出具签名）
3. 用工作流的 OIDC 身份做 keyless 签名（Fulcio 短时证书）
4. 把签名条目写进公共 Rekor 透明日志
5. 上传 sigstore bundle 与产物副本作为构建产物（保留 90 天）

## 当前状态（2026-11-27，一句话版）

| 项 | 读数 | 说明 |
|---|---|---|
| 已锚条目 | 4 条 | A-0000 / A-0001（v0.1 包）/ A-0002（规范化回执）/ A-0003（v0.3 包，logIndex 4143787841） |
| 最新候选包 | **v0.3.2，未锚** | 51 题，74,649 B，sha256 `5a24b20b9c42…`；空目录隔离自跑 51/51 |
| 判器分数 | 51/51（**同作者天花板**） | 外部模型盲判 50/51；傻瓜基线 0.5882 |
| 第三方实测（T1） | **0 件** | 所有 PASS 均为本机同操作者（T4），不是 T1 |
| `base.py` | **重建版** | `is_unusable / misused` 按唯一调用点重建，非原字节；已入包并明写 `engine_base_is_original: false` |
| SCITT | 形状对齐 | 无 Transparency Service 原生 COSE Receipt，**不声明任何规范符合性** |
| 口径 | 机器可审 | `tools/claim_audit.py`，禁语必须在否定语境，当前 9 个 md 命中 0 处 |

**A-0003 的正确说法**：锚的是 v0.3 内容的字节；该包内 `MANIFEST.json` 的版本号是旧值（写 0.1.0，实际 51 题），字节已进公共日志，不可改。

## 这条记录证明了什么

- 该产物的**确切字节**（sha256 可复算）
- 该产物**由本仓的这条工作流、在这个 commit、这个分支上产出**——证书里写死的身份形如
  `https://github.com/stevenzhao07/pccp-bench-anchors/.github/workflows/keyless-anchor.yml@refs/heads/main`
- 该记录在**某个时刻**进入了 append-only 公共日志，任何人可独立验算包含性证明、checkpoint 签名与 SET

## 没证明什么

- 不证明产物**内容正确**（哈希只保证"是这份字节"，不保证"这份字节是对的"）
- 不证明 PCCP 判定结论成立——判定本身由回执工具链另行校验
- 不证明这是**首次/最强**的任何事
- 仓库可见 ≠ 内容可信：信任来自"哈希 + 日志 + 可复算"，不是来自本 README

## 如何独立验证（不需要信任本仓）

见 `VERIFY.md`。最短路径：

```
cosign verify-blob --bundle xxx.sigstore.json \
  --certificate-identity-regexp 'https://github.com/stevenzhao07/pccp-bench-anchors/.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  artifact.bin
```

不装 cosign 也可以：bundle 里的条目结构与 Rekor 公共 API 一致，可直接取
`https://rekor.sigstore.dev/api/v1/log/entries?logIndex=...` 自己算 Merkle 路径。

## 目录

- `.github/workflows/keyless-anchor.yml` —— 锚定工作流（手动触发，参数可选）
- `VERIFY.md` —— 验算步骤与判据

## 边界

- 产物内容与许可跟随其上游（数据集 CC BY 4.0，代码 MIT）
- 本仓只放"锚定这件事"的记录，不放评测结论、不放厂商声明
- 任何对外表述必须写清缺口；未验证的一律标未验证

## repro/ —— 让别人算出同一个分

`repro/` 放三样东西，目标是"陌生人能自己重算 0.9688"：

- `adapter_reference.py`：可移植 adapter（引擎根按自身目录定位，不再是写死的本机路径）
- `lgd_engine/judges/`：`judge_pccp.py`（与发布包 snapshot **逐字节相同**，sha256 `7ee356ea…e3dd`）、
  `base.py`（原始字节 + 末尾重建块，块内有分隔标注）、`base.original.py`（不含重建块的原始字节）
- `run_repro.py`：直接 import 数据集包内的 `bench.py` 打分，不另写规则

实测：public 31/32 = 0.9688，masked 同分，两次 `case_digest` 相同。

**前提必须一起读**：判器需要 `base.py` 里的 `is_unusable / misused` 两个函数，而发布快照与本地引擎树不同源，
这两个函数在原始 base 里不存在。`repro/` 里的实现是**按唯一调用点重建**的，同分是旁证，不是"重建=原实现"。
要让"可复算"名副其实，下一步是把 base 原始字节纳入发布物并在 MANIFEST 登记 sha256。

## tools/ —— 每条判据各一个脚本，再收成一条命令

| 脚本 | 判据 | 它拦得住什么 |
|---|---|---|
| `verify_logid_binding.py` | logID == SHA-256(SPKI DER)，且与远端现取公钥同一把钥匙 | 换一把钥匙、把 logID 照抄 |
| `verify_rekor_inclusion.py` / `verify_anchor.py` | RFC 6962 自算路径 → 树根；checkpoint 签名 | 日志声称"在树里"但路径算不出来 |
| `verify_set.py` | 条目规范化 JSON 的 P-256 签名 | 伪造单条记录 |
| `verify_bundle.py` | 产物字节 == bundle digest == 条目 digest；issuer/SAN 身份 | "签名是真的，但签的是别的东西" |
| `verify_fulcio_chain.py` | leaf ← intermediate ← root（Sigstore 官方信任根） | 字段照抄的伪造证书 |
| `verify_all.py` | 上面全部 + （可选）回执十条判据 | 人肉判断"哪个输出算通过" |

一条命令：

```bash
python tools/verify_all.py \
  --entry anchor_entry_A0002.json --public-key rekor_publicKey.json \
  --bundle anchor_A0002.sigstore.json --artifact anchor_A0002_artifact.bin \
  --integrated-time 1795756228 \
  --expect-identity-regex '^https://github\.com/stevenzhao07/pccp-bench-anchors/'
```

输出是矩阵，最后一行 `ALL_PASS` / `HAS_FAIL`。任一项 FAIL 就不算通过——**不做加权、不取平均**。

## 零依赖验算（verify_zero_dep.py）

上面所有判据此前都依赖 `cryptography`（早期还依赖过 cosign / sigstore SDK）。为了让"外人可独立验算"不隐含"先装一堆东西"，`tools/verify_zero_dep.py` 只用 Python 标准库把六件事自己算完：

| 判据 | 算什么 |
|---|---|
| BINDING | 产物字节 sha256 == 条目 body 的摘要值 |
| LOGID_BINDING | logID == SHA-256(Rekor 公钥 SPKI DER) |
| INCLUSION | leaf → Merkle path → root == 条目 rootHash（RFC 6962） |
| CHECKPOINT | Rekor 公钥对 checkpoint 正文 ECDSA/SHA-256 |
| SET | 日志对四字段规范化 JSON 的签名 |
| CHAIN | leaf ← Fulcio intermediate ← root（P-384/SHA-384） |

P-256 与 P-384 曲线运算、DER 签名解析、X.509 证书拆解（TBS / SPKI / 签名算法 OID）全为手写，无第三方导入。

```bash
python tools/verify_zero_dep.py \
  --bundle bundle.json --artifact artifact.bin --entry entry.json \
  --rekor-key rekor_publicKey.json \
  --intermediate certs/fulcio_intermediate.pem --root certs/fulcio_root.pem
```

本机实跑 A-0001 与 A-0002，均 `ZERO_DEP_ALL_PASS`（六项全 OK）。负向变异：产物翻一字节 → 只有 BINDING 变 FAIL；条目 body 摘要改全 0 → INCLUSION 与 SET 同时 FAIL、CHECKPOINT 仍 OK（checkpoint 签的是树头不是这一条，属正确行为）。

`certs/` 下两张是 Fulcio 的中间与根证书（公开材料，取自官方 TUF 信任根），仅为免去使用者再自己去取。

## 题集判别力自审（红队，2026-11-27）

32 题公开集的审计结果，写在 `REDTEAM_DATASET_20261127.md`：

- 9 个布尔判据标志里 **6 个从没出现过另一种取值**（零方差）→ 只有装饰作用
- 答案分布 28 go / 4 hold / **0 reject** → "永远答 go"的傻瓜基线 = **28/32 = 0.8750**
- 判器 31/32 = 0.9688，与基线差值 **0.0938**
- 负例比例 4/32，Wilson 95% CI = [0.050, 0.281]

**因此本仓任何分数都必须带这句**：0.9688 表示"在这 32 题上复算一致"，不表示判定能力；比较任何外部结果时，先减掉 0.875 的白送分。

复现：`python tools/pccp_dataset_audit.py --zip pcb010.zip`
