# T1 接收协议（第三方实测，2026-11-27）

这份协议的唯一目的：让**与项目无关的人**在十分钟内自己产出 T1 证据，我方不再用"我自己重跑"顶替。

T1 的定义：操作者与项目无关系（非协作者、未参与撰写、未被我方指派跑数），在其本人机器上按下列
命令跑通并按模板回传。我方只做记录，不改写结果。

---

## 一、验算公共锚定（零第三方依赖，只需 Python 3.9+）

```bash
mkdir -p t1 && cd t1

# 1) 只从公网取工具与证书（不碰本机项目目录）
curl -sSLO https://raw.githubusercontent.com/stevenzhao07/pccp-bench-anchors/main/tools/verify_zero_dep.py
mkdir -p certs
curl -sSL  https://raw.githubusercontent.com/stevenzhao07/pccp-bench-anchors/main/certs/fulcio_intermediate.pem -o certs/fulcio_intermediate.pem
curl -sSL  https://raw.githubusercontent.com/stevenzhao07/pccp-bench-anchors/main/certs/fulcio_root.pem -o certs/fulcio_root.pem

# 2) 从公共 Rekor API 取条目（A-0002，logIndex 4142064557）
curl -sSL 'https://rekor.sigstore.dev/api/v1/log/entries?logIndex=4142064557' -o entry.json
curl -sSL 'https://rekor.sigstore.dev/api/v1/log/publicKey' -o rekor_publicKey.json

# 3) 跑
python tools/verify_zero_dep.py --entry entry.json --rekor-key rekor_publicKey.json \
  --intermediate certs/fulcio_intermediate.pem --root certs/fulcio_root.pem
```

期望最后一行：`ZERO_DEP_ALL_PASS`（六项 BINDING / LOGID_BINDING / INCLUSION / CHECKPOINT / SET / CHAIN）。
任一项 FAIL 即为 `HAS_FAIL`——不加权、不取平均，任一 FAIL 就是 FAIL。

## 二、验算数据集字节（可选，需下载数据集包）

```bash
# 取 v0.1 数据集包，核对声明的 sha256
sha256sum pccp-bench-0.1.0.zip
# 期望：1907e93a21305c3055777dda2f3c85f037501d821bba08abb37f7ac8127aaf61
```

## 三、回传模板（照填，不要改写字段名）

```json
{
  "t1_declaration": {
    "reviewer": "<你的名字或代号>",
    "independent": true,
    "relationship": "<与项目的关系，例：读到 GitHub 仓库，此前不认识作者>",
    "machine": "<操作系统 + Python 版本>",
    "checked_at": "<YYYY-MM-DDTHH:MM:SS+ZZ:ZZ>",
    "commands": ["<逐条贴你实际执行的命令>"],
    "steps": <执行的命令条数>,
    "steps_rc0": <返回码为 0 的命令条数>,
    "results": {
      "zero_dep_verify": "ZERO_DEP_ALL_PASS | HAS_FAIL（贴最后一行）",
      "dataset_sha256": "<你算出来的值>"
    },
    "disagreements": "<有没有对不上的地方，如实写；没有就写 none>"
  }
}
```

回传渠道：在仓库开一个 Issue 贴上述 JSON（标题以 `T1` 开头），或在任何公开渠道贴出并给链接。

## 四、我方接到后怎么记

1. 只记你回传的原话，不做润色；对不上的地方单独列一行。
2. 记进 `T1_LEDGER.md`：reviewer / checked_at / 结果 / 差异项。
3. 只有这份回传存在，G5 / S4 才从 NOT RUN 变成"有分母"。**在那之前，任何"外人实测"字样都不许出现在我方文件里。**

## 五、边界（先说清，免得白跑）

- 这份协议验证的是**锚定与可复算**，不验证判定标准本身对不对。
- 题目标签由我方标注，你没有义务认同；你只验"字节有没有进公共日志、能不能独立验出来"。
- 不涉及任何账号、密钥或登录；全流程只读公网。
