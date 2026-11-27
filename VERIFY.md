# VERIFY.md —— 怎么独立验算一条锚定

前提：你不需要信任本仓，也不需要信任我。只需要网络和一个能跑 sha256 的环境。

## 一、只验"字节对不对"

```bash
sha256sum artifact.bin
# 与工作流日志里打印的 sha256 比对；与上游宣称的哈希比对
```

这一步不涉及签名，纯算。

## 二、验签名身份（装 cosign）

```bash
cosign verify-blob \
  --bundle artifact.bin.sigstore.json \
  --certificate-identity-regexp 'https://github.com/stevenzhao07/pccp-bench-anchors/.github/workflows/keyless-anchor.yml@.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  artifact.bin
```

要点：

- `--certificate-oidc-issuer` **必须写** `https://token.actions.githubusercontent.com`。
  不写 issuer 等于"任何有 sigstore 身份的人签的都算"——那不是验证。
- identity 用 regexp 匹配到本仓的这条工作流文件；换成别的仓、别的 workflow 就不该通过。

## 三、不装 cosign 的验法（三条各自独立）

1. **包含性**：`GET https://rekor.sigstore.dev/api/v1/log/entries?logIndex=<n>`
   取回条目，自己按 RFC 6962 算叶子哈希与路径，得到树根，与同批取回的 checkpoint 里的树根比。
2. **checkpoint 签名**：checkpoint 正文用 Rekor 公钥（`/api/v1/log/publicKey`）验 ECDSA P-256/SHA-256。
   checkpoint 被签的是**正文 + 尾随换行**，名字与时间戳不在签名范围内——所以改名字不会让验签失败，这不叫"通过"。
3. **SET**：对 `{body, integratedTime, logID, logIndex}` 的规范化 JSON（键排序、无空格）验签。
   注意 `record.logIndex` 与 `proof.logIndex` 在公共实例上可能不一致（proof 按较新树快照算），
   **以绑定为准，不要拿 index 当唯一标识**。
4. **绑定**：条目里 `artifactHash`（或 hashedrekord 的 digest）必须等于产物字节的 sha256。
   这一条对不上，前面三条全过也没意义——签的是别的东西。

## 四、这三条最常见的假通过

- 只看"有签名文件"就认为通过（签名文件可以随便生成）
- 只看 index 对得上，不验绑定（index 只是提示）
- 验了 checkpoint 就认为条目也被签（checkpoint 签的是树根，不是每一条）
- 把 `SET` 的"存在"当"正确"（存在不代表验签通过）

## 五、本仓锚定的边界（写在正文，不藏在脚注）

- 锚定只保证"这份字节由这条工作流在某时刻产出"，**不保证内容正确**
- 工作流取回的产物若上游被替换，sha256 校验会拦住；但上游若同时改了宣称值与文件，锚定拦不住——
  这是"同一时间点的一致性"，不是"历史正确性"
- 保留期 90 天的构建产物会过期；**Rekor 条目不会消失**，条目与哈希仍可查
