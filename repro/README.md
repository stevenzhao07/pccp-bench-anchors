# repro/ —— 让 0.9688 可被外人重算

这个目录回答一个具体问题：**别人拿到数据集包，能不能算出同一个分？**

原来的答案是"不能"，有两个原因，现在各自有了处置：

| 阻塞 | 现状 | 处置 |
|---|---|---|
| adapter 把引擎根写死成 `D:\Workbuddy\...\lgd-engine` | 除作者外没人有这个路径 | `adapter_reference.py` 改为按**自身目录**定位引擎 |
| 判器 `judge_pccp.py` 依赖 `base.py` 里的 `is_unusable / misused`，而发布快照与本地引擎树**不同源**（本地 base 里根本没有这两个函数） | 导入即 `ImportError`，跑不起来 | 按唯一调用点重建这两个函数，**明确标注为重建、非原字节** |

## 组成

```
repro/
├── adapter_reference.py         # 可移植 adapter（逻辑与原版逐字一致，仅改引擎根定位）
├── lgd_engine/judges/
│   ├── judge_pccp.py            # 引擎字节：取自发布包 snapshot/judge_pccp.py
│   ├── base.py                  # 已发布的 base.py + 末尾重建块（有分隔标注）
│   └── base.original.py         # 原始 base.py（不含重建块，供比对）
└── run_repro.py                 # 直接 import 数据集包里的 bench.py 打分，不另写规则
```

## 字节身份

- `judge_pccp.py`：与 `pccp-bench_zenodo_v0.1.0.zip` 内 `snapshot/judge_pccp.py` **逐字节相同**
- `base.original.py`：取自本机引擎树 `lgd-engine/lgd_engine/judges/base.py`
- `base.py`：`base.original.py` + RECONSTRUCTED 块（分界注释保留在文件里）

## 跑法

```bash
python run_repro.py --dataset-zip pccp-bench_zenodo_v0.1.0.zip
```

实测（本机，2026-11-27）：

```
n_cases 32
public  exact 31/32 → 0.9688    misses: K260973-H1-DICE-MISS   tag_rate 1.0
masked  exact 31/32 → 0.9688    misses: K260973-H1-DICE-MISS   tag_rate 1.0
case_digest ba7f9313e4fe26a47d040ec2db23ece27d65f5d83578b24ab88ec4d051164e29
```

`public` 与 `masked` 同分，说明这个分数**不靠记住具体案子**——遮掉提交号、器械名后不掉分。

## 这份复算证明了什么、不证明什么

**证明**：在"重建的两个辅助函数"这一前提下，31/32 这个数与公布值一致；且两列同分。
**不证明**：
- 不证明重建函数与原实现**逐字一致**——原实现从未公开，重建只有调用点一个依据。同分是**旁证**，不是等价证明。
- 不能复算 hidden 列：隐藏题集未随包发布，包里只有 `hidden_commitment.json`（哈希承诺），
  所以"42 题全量分"无法由外人重算，只有 32 题公开集可复算（前提：本目录内的重建版 `base.py`）。
- 不能复算历史上任何一次带时间戳的跑分——本工具是**当下重算**，不是回放。

## 要真正"端到端可复算（含前提）"，还差一件

把 base.py 的**原始字节**（含那两��函数）作为发布物的一部分放进包，并在 `MANIFEST.json` 里登记其 sha256。
在那之前，任何"我们可复算"的表述都必须带上"重建前提"四个字。
