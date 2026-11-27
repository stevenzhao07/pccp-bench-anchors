# pccp-bench-anchors

PCCP-bench 产物的**锚定记录仓**。每次锚定由本仓的一条 GitHub Actions 工作流完成：

1. 取回指定产物（默认 PCCP-bench v0.1.0 数据集 zip）
2. 校验 sha256（与期望值不符则直接失败，不产出具签名）
3. 用工作流的 OIDC 身份做 keyless 签名（Fulcio 短时证书）
4. 把签名条目写进公共 Rekor 透明日志
5. 上传 sigstore bundle 与产物副本作为构建产物（保留 90 天）

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
