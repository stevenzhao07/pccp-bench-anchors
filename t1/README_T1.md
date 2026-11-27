# T1 复核包使用说明（2026-11-27，v2）

这份包是给**与项目无关的人**用的。你不需要认同任何结论，也不需要读我们的代码。
你只需要做下面两件事之一，然后把结果原样回传。

- **A 路径（10 分钟）**：跑三条命令，看能不能验出来。
- **B 路径（30 分钟）**：如果你手上有一份真实的 PCCP 变更档案（脱敏即可），按 14 格填，我们给你跑一次判决。

跑不通就写跑不通。我们照原样记进台账，不会写成"已验证"。

---

## 路径 A：验一条公共锚定（只需 Python 3.9+，无第三方库）

```bash
mkdir -p t1 && cd t1
cp -r <包内>/tools .
mkdir -p certs && cp <包内>/certs/*.pem certs/

# 取 A-0003 这条公共记录（logIndex 4143787841）与日志公钥
curl -sSL 'https://rekor.sigstore.dev/api/v1/log/entries?logIndex=4143787841' -o entry.json
curl -sSL 'https://rekor.sigstore.dev/api/v1/log/publicKey' -o rekor_publicKey.json

python tools/verify_zero_dep.py --entry entry.json --rekor-key rekor_publicKey.json \
  --intermediate certs/fulcio_intermediate.pem --root certs/fulcio_root.pem
```

期望最后一行：`ZERO_DEP_ALL_PASS`（六项：BINDING / LOGID_BINDING / INCLUSION / CHECKPOINT / SET / CHAIN）。
任一项 FAIL 就是 `HAS_FAIL`——不加权、不取平均。

**它证明什么**：这些字节确实在某时刻进了公共透明日志，且可以被独立重算。
**它不证明什么**：内容对不对、是谁发的、判据好不好。这三件都不在这三条命令里。

## 路径 A+：跑数据集包本身

```bash
unzip pccp-bench_v0.3.2_candidate.zip -d pkg && cd pkg
python -I dataset/selfcheck.py
```

期望：`verdict_match 51/51`、`tag_rate 1.0000`、`SELFCHECK_ALL_PASS`（退出码 0）。
`-I` 是隔离解释器：不继承你的环境变量和 site-packages，所以"能跑"不靠你本机装了什么东西。

## 路径 B：给一份真实变更档案的 14 格

`t1_encode_template.csv` 有 14 行，每行一格。填法只有两条规矩：

1. **填不出就留空**，不要猜。留空我们按"必填缺失"处理（判器会给 hold），这是预期行为。
2. **每格附一句原文引用**（`quote` 列），引用要能在你给的文件里找到。找不到就留空。

为什么这么严：这 14 格里有 4 格（授权范围、判据是否达成、是否仍实质等同、证据够不够）
是**判断**，不是字面。判断只能由人做，我们不做，也不替你猜。

## 回传

把 `t1_return_template.json` 填好，连同你的运行输出（纯文本贴进去即可）回传：

- 仓库 Issue，标题以 `T1` 开头；
- 或直接回邮件。

回传后我们会做两件事，并且只做这两件：
1. `verify_t1_return.py` 检查回传是否完整（缺项就退回，不"代为补全"）；
2. 原话记进 `T1_LEDGER.md`，包括跑不通的情况。

## 三条我们主动写明的边界

1. **这是 T4 还是 T1**：你跑 = T1；我们跑 = T4。两者在台账里分开记，不混。
2. **我们不替你解释结果**：你说 FAIL，台账就记 FAIL，不写"可能是网络问题"。
3. **我们不拿你的名字做背书**：台账记你的关系自述，不写"某专家认可"。
