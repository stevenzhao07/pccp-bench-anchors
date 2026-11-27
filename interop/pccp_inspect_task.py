#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pccp_inspect_task.py —— 把 pccp-bench 的判定包成 Inspect AI 的一个 task。

为什么这么做：T1（第三方实测）缺的不是技术，是**动手成本**。
Inspect 是 UK AISI 开源、第三方评测者的通用框架（entry point 可扩展、240+ 贡献者）。
把判定包成 task 之后，别人只需一条命令：

    inspect eval pccp_inspect_task.py@pccp_scope --model mockllm/model

模型在这里不参与判断（判定由判器算，模型只被"占位"），所以任何人跑出来结果相同——
相同就对了：我们要的是"可复算"，不是"模型表现"。

依赖：inspect_ai（pip install inspect_ai）；包本身在 dist/pccp-bench_v0.3.2_candidate.zip。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import zipfile

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.scorer import CORRECT, INCORRECT, Score, Target, accuracy, scorer, stderr
from inspect_ai.solver import Generate, TaskState, solver

PKG = os.environ.get("PCCP_PKG", "dist/pccp-bench_v0.3.2_candidate.zip")

_STATE: dict = {}


def _load_pkg() -> str:
    """把包解到临时目录并让 adapter 可导入。返回根目录。"""
    if "root" in _STATE:
        return _STATE["root"]
    root = tempfile.mkdtemp(prefix="pccp_inspect_")
    with zipfile.ZipFile(PKG) as z:
        z.extractall(root)
    if root not in sys.path:
        sys.path.insert(0, root)
    _STATE["root"] = root
    return root


def _adapter():
    _load_pkg()
    from dataset import adapter_reference           # noqa: F401
    return adapter_reference


def _cases() -> list:
    root = _load_pkg()
    with open(os.path.join(root, "dataset", "cases_public.json"), encoding="utf-8") as f:
        return json.load(f)["cases"]


FIELDS = ["pccp_authorized", "claimed_pccp_coverage", "actually_within_scope",
          "criteria_measured", "criteria_met", "affects_intended_use",
          "change_class_described", "acceptance_criteria_met", "remains_se_to_predicate",
          "validation_documented", "labeling_version_history", "udi_updated",
          "change_type", "evidence_sufficiency", "jurisdiction", "source_refs"]


def _ctx(case: dict) -> dict:
    return {k: case[k] for k in FIELDS if k in case}


def _question(case: dict) -> str:
    return ("Device: %s\nChange type: %s\nMay this change be implemented under an authorized "
            "Predetermined Change Control Plan (PCCP), or does it need its own marketing submission?"
            % (case.get("device_description", "")[:400], case.get("change_type")))


@solver
def pccp_judge():
    ad = _adapter()

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        res = ad.evaluate(state.metadata["ctx"])
        verdict = res.get("verdict", "")
        state.output.completion = verdict
        state.metadata["verdict"] = verdict
        state.metadata["tag"] = res.get("tag")
        state.metadata["encoding_conflicts"] = res.get("_encoding_conflicts")
        return state

    return solve


@scorer(metrics=[accuracy(), stderr()])
def pccp_match():
    async def score(state: TaskState, target: Target) -> Score:
        got = (state.output.completion or "").strip()
        exp = (target.text or "").strip()
        return Score(
            value=CORRECT if got == exp else INCORRECT,
            answer=got,
            explanation="expected=%s got=%s tag=%s" % (exp, got, state.metadata.get("tag")),
        )

    return score


@task
def pccp_scope() -> Task:
    samples = [
        Sample(input=_question(c), target=c["expected_verdict"], id=c["case_id"],
               metadata={"ctx": _ctx(c), "kind": c.get("kind"),
                         "expected_tag": c.get("expected_tag")})
        for c in _cases()
    ]
    return Task(dataset=MemoryDataset(samples, name="pccp-bench-v0.3.2"),
                solver=[pccp_judge()], scorer=pccp_match())
