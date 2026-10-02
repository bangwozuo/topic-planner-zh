# -*- coding: utf-8 -*-
"""
选题库去重匹配流程 —— 端到端编排脚本。

编排逻辑（与 SKILL.md 的 DAG 一致）：
  WF1 候选池（daily_pool.json）或用户粘贴候选
  → [topic-dedup-check] 字面查重：二元组相似度 0.60/0.40 分级 + 90 天重做窗口
  → 内置：三因子评分（时效衰减 × 垂直相关 × 竞争度反向，≥70 冲 / 55-70 备选 / <55 弃）
  → [topic-knowledge-base] 产出入库操作建议（待人工确认，AI 不直接改库）
  → 去重后选题榜.xlsx + dedup_match_result.json

失败处理：
  - 上游脚本退出码 != 0 → 中止并打印 stderr（不静默失败）
  - 上游 JSON 产物缺失/损坏 → 中止并提示重跑上游
  - 历史库为空 → 提示「新账号」后全部候选直接进评分
  - 候选全被查重淘汰 → 输出空榜与淘汰说明，正常退出（不硬凑）

用法：
  python run_flow.py --input input.json --outdir out
  python run_flow.py --demo
"""
from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FLOW_DIR = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(FLOW_DIR))
sys.path.insert(0, os.path.join(REPO, "lib"))

try:
    import assettools as at
except ImportError:  # pragma: no cover
    print("[错误] 未找到 lib/assettools.py", file=sys.stderr)
    sys.exit(2)

DEDUP_SCRIPT = os.path.join(REPO, "skills", "topic-dedup-check", "scripts", "dedup_check.py")

GRADE_GO, GRADE_BACKUP = 70, 55
HALF_LIFE_H = 48
W_TIMELINESS, W_VERTICAL, W_COMPETITION = 0.4, 0.3, 0.3


def score_candidate(c: dict) -> dict:
    """内置步骤：三因子评分（数值全部在此计算，模型不口算）。

    得分 = 时效衰减分×0.4 + 垂直相关分×0.3 + 竞争度反向分×0.3
    - 时效分：0.6 + 0.4 × 0.5^(h/48)，常青题（evergreen=true）恒 0.85
    - 垂直分：match 0-1 × 100
    - 竞争度分：<20 条同类内容满分，>200 条零分，中间线性
    """
    title = c.get("title", "")
    match = float(c.get("match", 0.8)) * 100
    n_same = float(c.get("same_topic_count", 50))
    if n_same <= 20:
        comp = 100.0
    elif n_same >= 200:
        comp = 0.0
    else:
        comp = (200 - n_same) / 180 * 100

    evergreen = bool(c.get("evergreen", False))
    if evergreen:
        timeliness, note_t = 85.0, "常青题，时效恒定"
    else:
        h = float(c.get("hours_since", 0))
        timeliness = (0.6 + 0.4 * (0.5 ** (h / HALF_LIFE_H))) * 100
        note_t = f"首发 {h:.0f}h，时效系数 {timeliness:.0f}"

    score = timeliness * W_TIMELINESS + match * W_VERTICAL + comp * W_COMPETITION
    if score >= GRADE_GO:
        level = "A 冲"
    elif score >= GRADE_BACKUP:
        level = "B 备选"
    else:
        level = "C 弃"
    return {
        "选题": title,
        "来源": c.get("source", ""),
        "时效分": round(timeliness, 1),
        "垂直分": round(match, 1),
        "竞争度分": round(comp, 1),
        "总分": round(score, 1),
        "级别": level,
        "时效说明": note_t,
    }


def main():
    ap = argparse.ArgumentParser(description="选题库去重匹配流程")
    ap.add_argument("--input", help="流程输入 JSON（candidates/library）")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()

    at.ensure_outdir(a.outdir)
    if a.demo:
        from run_flow import DEMO as payload
    elif a.input:
        payload = at.read_json(a.input)
    else:
        ap.error("需要 --input / --demo 之一")

    candidates = payload.get("candidates", [])
    library = payload.get("library", [])
    if not candidates:
        ap.error("缺少 candidates：请提供候选选题清单（可来自 WF1 的 daily_pool.json）")

    # 步骤 1：字面查重（topic-dedup-check）
    dedup_in = os.path.join(a.outdir, "_step_dedup_input.json")
    at.write_json({"candidates": candidates, "library": library}, dedup_in)
    r = subprocess.run(
        [sys.executable, DEDUP_SCRIPT, "--input", dedup_in, "--outdir", a.outdir],
        cwd=FLOW_DIR, capture_output=True, text=True, timeout=180,
    )
    if r.returncode != 0:
        print(f"[失败处理] 上游技能 topic-dedup-check 退出码 {r.returncode}，流程中止。", file=sys.stderr)
        print(r.stderr[-800:], file=sys.stderr)
        sys.exit(1)
    dedup_json = os.path.join(a.outdir, "dedup_check.json")
    if not os.path.exists(dedup_json):
        print(f"[失败处理] 上游产物 {dedup_json} 缺失，流程中止（请重跑上游技能）。", file=sys.stderr)
        sys.exit(1)
    dedup = at.read_json(dedup_json)
    print("步骤 1  topic-dedup-check   ✅  → dedup_check.json")

    # 步骤 2（内置）：通过的候选进三因子评分；重复项标淘汰
    dedup_rows = {row["候选选题"]: row for row in dedup.get("rows", [])}
    scored, dropped = [], []
    for c in candidates:
        d = dedup_rows.get(c.get("title", ""), {})
        verdict = d.get("判定", "🟢 通过")
        if verdict.startswith("🔴"):
            dropped.append({"选题": c.get("title", ""), "原因": f"查重{verdict}；{d.get('说明', '')}"})
            continue
        row = score_candidate(c)
        row["查重"] = "通过" if verdict.startswith("🟢") else "相似可重做"
        scored.append(row)
    scored.sort(key=lambda x: -x["总分"])
    for i, row in enumerate(scored, 1):
        row["#"] = i

    # 步骤 3：知识库入库建议（待人工确认，AI 不直接改库）
    lib_ops = []
    for row in scored:
        if row["级别"] in ("A 冲", "B 备选"):
            lib_ops.append({
                "操作": "新增入库（待人工确认）",
                "条目": row["选题"],
                "选题ID": f"T{1000 + len(library) + len(lib_ops) + 1}",
                "理由": f"{row['级别']} {row['总分']} 分；来源 {row['来源']}；查重{row['查重']}",
            })
    for d in dropped:
        lib_ops.append({"操作": "淘汰（查重未过）", "条目": d["选题"], "选题ID": "—", "理由": d["原因"]})

    summary = {
        "候选数": len(candidates),
        "历史库条数": len(library) if library else 0,
        "查重淘汰": len(dropped),
        "进评分": len(scored),
        "A 冲": sum(1 for x in scored if x["级别"] == "A 冲"),
        "B 备选": sum(1 for x in scored if x["级别"] == "B 备选"),
        "C 弃": sum(1 for x in scored if x["级别"] == "C 弃"),
        "入库建议": sum(1 for x in lib_ops if x["操作"].startswith("新增")),
        "说明": "入库建议全部待人工确认；历史库为空时查重自动通过" if not library else "数值以脚本输出为准",
    }

    xlsx = at.write_excel(
        os.path.join(a.outdir, "去重后选题榜.xlsx"),
        {
            "选题榜": scored or [{"选题": "（候选全部被查重淘汰）"}],
            "查重淘汰": dropped or [{"选题": "（无）", "原因": "—"}],
            "入库建议": lib_ops or [{"操作": "（无）"}],
            "汇总": [{"项": k, "内容": str(v)} for k, v in summary.items()],
        },
        highlights={"选题榜": {"级别": "contains:A 冲"},
                    "入库建议": {"操作": "contains:新增"}},
        widths={"选题榜": {"选题": 40, "时效说明": 26},
                "入库建议": {"条目": 40, "理由": 40}},
    )
    js = at.write_json({"summary": summary, "ranked": scored, "dropped": dropped,
                        "lib_ops": lib_ops, "generated_at": at.stamp(),
                        "note": "评分与查重均来自上游脚本/内置计算，入库建议待人工确认"},
                       os.path.join(a.outdir, "dedup_match_result.json"))
    print("步骤 2  三因子评分（内置）    ✅")
    print("步骤 3  知识库入库建议        ✅")
    print(f"汇总    候选 {summary['候选数']} → 查重淘汰 {summary['查重淘汰']}，"
          f"A 冲 {summary['A 冲']} / B 备选 {summary['B 备选']} / C 弃 {summary['C 弃']}")
    print(" 产物:", xlsx)
    at.emit({"files": [xlsx, js], "summary": summary})


DEMO = {
    "candidates": [
        {"title": "00后整顿职场：拒绝无效加班从这3句话开始", "source": "平台热榜", "match": 0.9, "same_topic_count": 35, "hours_since": 9},
        {"title": "面试官最后问「你有什么问题吗」怎么答", "source": "搜索下拉词", "match": 0.95, "same_topic_count": 12, "evergreen": True},
        {"title": "面试被问期望薪资怎么答：3 个话术模板", "source": "评论区高赞提问", "match": 0.85, "same_topic_count": 40, "evergreen": True},
        {"title": "被裁员那天我在工位坐到凌晨：3 个动作保住赔偿金", "source": "竞品爆款拆解", "match": 0.9, "same_topic_count": 8, "hours_since": 30},
        {"title": "国庆假期后第一天上班，怎么快速找回状态", "source": "节点日历", "match": 0.75, "same_topic_count": 150, "hours_since": 2},
    ],
    "library": [
        {"title": "面试被问期望薪资怎么答：3 个话术模板", "days_ago": 35},
        {"title": "裁员赔偿金谈判：N+1 怎么算", "days_ago": 50},
        {"title": "汇报工作先说结论：金字塔原理的 3 步用法", "days_ago": 120},
        {"title": "节后综合症自救指南", "days_ago": 200},
    ],
}


if __name__ == "__main__":
    main()
