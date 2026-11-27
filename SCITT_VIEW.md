# SCITT_VIEW —— Rekor 条目 → 收据语义的显式映射

这份文件的用途只有一个：把"我们有什么"和"SCITT 要什么"逐字段对上，让外人不用读我们的代码也能重算。

---

## 一、三件套对位

| SCITT 概念 | 我们手上的东西 | 状态 |
|---|---|---|
| Statement | 产物 sha256 写进 Rekor 条目 `spec.data.hash`；另有独立 COSE_Sign1 版 `statement_A0003.cose` | 有，但两套密钥不通 |
| Transparency Service | Rekor（`rekor.sigstore.dev`），log_id `c0d23d6a…1801d` | 有 |
| Receipt | **没有原生 COSE Receipt** → 做显式映射 | 映射，不是原生 |

## 二、逐字段映射规约（`scitt_view.py` 的实质约定）

```
statement.subject_sha256  ← spec.data.hash.value
statement.media_type      ← spec.data.hash.algorithm
ts.uri                    ← https://rekor.sigstore.dev
ts.log_id                 ← 条目 logID
receipt.leaf_index        ← 条目 logIndex
receipt.tree_size         ← verification.inclusionProof.treeSize
receipt.root_hash         ← verification.inclusionProof.rootHash
receipt.inclusion_path    ← verification.inclusionProof.hashes
receipt.checkpoint        ← verification.inclusionProof.checkpoint（签名者 = 日志公钥）
receipt.set               ← verification.signedEntryTimestamp（签名者 = 日志公钥）
```

不进映射的：`spec.signature`（提交者的 Fulcio 签名）。它属于 Statement 归属，不属于收据；工具照抄进 `provenance`，并明确标注"不由本工具验证"。

**为什么这样切**：收据要回答的是"这条记录在某个时刻确实在某棵树里"，签名归属是另一个问题。混在一起，等于用"我能验签名"冒充"我能验收据"。

## 三、自验四项（零第三方依赖）

| 项 | 怎么算 | A-0003 结果 |
|---|---|---|
| STATEMENT | 产物 sha256 == `subject_sha256` | OK |
| INCLUSION | leaf_index + path + tree_size → root_hash | OK（depth 26） |
| CHECKPOINT | checkpoint 正文签名（日志公钥） | OK |
| SET | 条目规范化 JSON 签名（日志公钥） | OK |

`SCITT_VIEW_ALL_PASS`。视图落盘 `out/scitt_view_A0003.json`，第一行就写 `_native_cose_receipt: false`。

## 四、矩阵扩到八行

`verify_all.py` 新增两行：`SCITT_STATEMENT`（COSE 签验 + 载荷绑定）与 `RECEIPT_VIEW`（映射自验）。仍是**任一项 FAIL 即整体 FAIL**，不加权、不取平均。

实测：

```
正向 8 行 ALL_PASS，退出码 0
负向（产物翻一字节）→ BINDING / SCITT_STATEMENT / RECEIPT_VIEW 三项 FAIL，其余仍 OK，退出码 1
```

负向只翻三项而不是全部翻——正说明各判据互相独立，没有一条在替另一条背书。

## 五、顺手修掉一个真问题

首次跑八行时 `LOGID_BINDING` 报空、`INCLUSION`/`CHECKPOINT` 报 FAIL。原因不是数据坏，是**文件形态**：老判据（`verify_anchor`/`verify_set`/`verify_logid_binding`）只吃 Rekor 原始形态 `{uuid: rec}`，零依赖判据只吃摊平形态（rec 本身）。同一份事实两种壳，靠人记"该喂哪个文件"必然出事。

改法：`verify_all.py` 里加 `normalize_entry()`，两种形态自动归一，各喂各的。改完八行全通。这条记进正文，不藏脚注——因为它说明的是"我们的判据曾经对文件壳敏感"。

## 六、边界（必须写在明面上）

- **T1 = 0 件**，八行 PASS 全是本机干跑（T4）。
- Statement 签名用的是一次性测试密钥，**不是** Fulcio/OIDC 身份；正式锚定身份在 A-0001/A-0003 的 Fulcio 证书，两套密钥不通，不能互相顶替。
- 不是原生 COSE Receipt，不声明任何 SCITT 规范符合性；`scitt_profile.json` 只是自述 profile。
- SCT 签名仍不可验（原因已定），本文件不作任何 CT 通过声明。

## 七、下一层

1. 若日志服务侧支持 SCITT 的 statement 注册语义，把 `statement_A0003.cose` 直接提交，换回原生 receipt（这需要先解决身份：测试密钥换 OIDC）。
2. 把 `scitt_profile.json` 变成可由脚本自检的：profile 里每条 claimed 都指向一个可执行命令，`verify_profile.py` 逐条跑、逐条判。
3. T1：`T1_INVITE_DRAFT.md` 指着这套八行矩阵，请一个人在自己机器上跑一遍。
