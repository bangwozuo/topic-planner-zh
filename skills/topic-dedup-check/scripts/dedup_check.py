# -*- coding: utf-8 -*-
"""
选题去重校验 —— 候选选题与历史选题库的相似度比对器。

职责边界：本脚本只做**确定性计算与产物生成**（去标点二元组相似度、分级判定、
排序出表）。相似的两条题算不算「同一题的不同角度」、差异化角度怎么改、
要不要合并，由模型按 prompt.txt 完成（模型的强项）。

核心规则（与 prompt.txt 一致）：
  - 相似度 ≥ 0.60 → 🔴 重复（淘汰或与旧题合并）
  - 0.40 - 0.60  → 🟡 相似（保留但必须换角度：换人群/换场景/换步骤数/换结果）
  - < 0.40       → 🟢 通过
  - 历史库超过 90 天的条目自动降一档（旧题复活窗口：90 天前的题可重做）

用法：
  python dedup_check.py --input input.json --outdir out
  python dedup_check.py --demo                # 用内置样例跑一遍

产物：
  out/选题去重清单.xlsx   判定明细 / 汇总 两 sheet（重复行标红）
  out/dedup_check.json    机器可读结果（供 topic-lib-dedup-match-flow 读取）
"""
from __future__ import annotations

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(SKILL_DIR))
sys.path.insert(0, os.path.join(REPO, "lib"))

try:
    import assettools as at
except ImportError:  # pragma: no cover
    print("[错误] 未找到 lib/assettools.py。请确认技能位于 <repo>/skills/<slug>/scripts/ 下，"
          "且 <repo>/lib/assettools.py 存在。", file=sys.stderr)
    sys.exit(2)

DUP_T = 0.60      # 重复阈值
SIM_T = 0.40      # 相似阈值
REVIVE_DAYS = 90  # 超过 90 天的历史题可重做（降一档）

_PUNCT = re.compile("[\\s，。：:；;、！!？?「」『』“”‘’·,.\\-—|]")

# 差异化角度词表（模型在标注里引用这些方向）
ANGLE_HINTS = ["换人群", "换场景", "换步骤数", "换结果", "换立场", "换失败面"]


def _ngrams(s: str) -> set:
    s = _PUNCT.sub("", s)
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else {s}


def _similarity(a: str, b: str) -> float:
    """去标点二元组：Jaccard 与包含度取大。长标题改写短标题也能命中。"""
    sa, sb = _ngrams(a), _ngrams(b)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    return max(inter / len(sa | sb), inter / min(len(sa), len(sb)))


def check(payload):
    candidates = payload.get("candidates", [])
    library = payload.get("library", [])
    if not candidates:
        raise SystemExit("[错误] candidates 为空：请提供候选选题（title）")
    if not library:
        print("[提示] 历史库为空（新账号首条内容）：全部候选直接判通过。")

    rows = []
    for c in candidates:
        ctitle = str(c.get("title", ""))
        best, best_sim = None, 0.0
        for lib in library:
            s = _similarity(ctitle, str(lib.get("title", "")))
            if s > best_sim:
                best, best_sim = lib, s
        lib_days = float(best.get("days_ago", 0)) if best else 0

        # 90 天外的历史题降一档（同题重做窗口）
        if best is None:
            level, sim_out, verdict = "🟢 通过", 0.0, "库内无近似题"
        else:
            sim_out = round(best_sim, 2)
            if best_sim >= DUP_T:
                verdict = f"与《{best.get('title', '')}》高度重合（{lib_days:.0f} 天前）"
                level = "🟡 相似（可重做）" if lib_days > REVIVE_DAYS else "🔴 重复"
            elif best_sim >= SIM_T:
                verdict = f"与《{best.get('title', '')}》部分重合（{lib_days:.0f} 天前）"
                level = "🟢 通过（建议换角度）" if lib_days <= REVIVE_DAYS else "🟢 通过"
            else:
                verdict = "库内最接近的题重合度低"
                level = "🟢 通过"

        rows.append({
            "候选选题": ctitle,
            "来源": c.get("source", ""),
            "最高相似度": sim_out,
            "最接近的历史题": best.get("title", "") if best else "",
            "历史题距今(天)": lib_days,
            "判定": level,
            "说明": verdict,
        })

    # 差异化建议：重复/相似的候选项由模型按 ANGLE_HINTS 给方向，脚本只标注需要建议
    for r in rows:
        if r["判定"].startswith("🔴"):
            r["说明"] += "；差异化方向：" + "、".join(ANGLE_HINTS[:3])
        elif r["判定"].startswith("🟡"):
            r["说明"] += "；90 天窗口已过，可换角度重做"

    rows.sort(key=lambda r: -r["最高相似度"])
    for i, r in enumerate(rows, 1):
        r["#"] = i

    summary = {
        "候选数": len(rows),
        "历史库条数": len(library),
        "重复": sum(1 for r in rows if r["判定"].startswith("🔴")),
        "相似(可重做)": sum(1 for r in rows if r["判定"].startswith("🟡")),
        "通过": sum(1 for r in rows if r["判定"].startswith("🟢")),
        "阈值": f"重复 ≥{DUP_T}；相似 {SIM_T}-{DUP_T}；重做窗口 >{REVIVE_DAYS} 天",
        "建议": "重复项淘汰或合并；相似项换角度重做；通过项进下一步评分",
    }
    return rows, summary


def build(payload, outdir):
    rows, summary = check(payload)
    at.ensure_outdir(outdir)
    xlsx = at.write_excel(
        os.path.join(outdir, "选题去重清单.xlsx"),
        {
            "判定明细": rows or [{"候选选题": "（无候选）"}],
            "汇总": [{"项": k, "内容": str(v)} for k, v in summary.items()],
        },
        highlights={"判定明细": {"判定": "contains:重复"}},
        widths={"判定明细": {"候选选题": 36, "最接近的历史题": 36, "说明": 40}},
    )
    js = at.write_json({"summary": summary, "rows": rows,
                        "rules": f"二元组相似度：重复≥{DUP_T}，相似{SIM_T}-{DUP_T}；90天重做窗口",
                        "generated_at": at.stamp(),
                        "note": "机器相似度结果；同题异角度的语义判断与差异化方向须由模型按 prompt.txt 复核"},
                       os.path.join(outdir, "dedup_check.json"))
    return {"files": [xlsx, js], "summary": summary, "rows": rows}


DEMO = {
    "candidates": [
        {"title": "面试被问期望薪资怎么答：3 个话术模板", "source": "热榜候选"},
        {"title": "被裁员那天我在工位坐到凌晨：3 个动作保住赔偿金", "source": "竞品爆款"},
        {"title": "面试必问的 5 个问题及回答模板", "source": "搜索下拉词"},
        {"title": "领导让你口头汇报时，先说结论再说理由", "source": "评论区提问"},
        {"title": "国庆假期后第一天上班，怎么快速找回状态", "source": "节点日历"},
    ],
    "library": [
        {"title": "面试被问期望薪资怎么答：3 个话术模板", "days_ago": 35},
        {"title": "裁员赔偿金谈判：N+1 怎么算", "days_ago": 50},
        {"title": "汇报工作先说结论：金字塔原理的 3 步用法", "days_ago": 120},
        {"title": "节后综合症自救指南", "days_ago": 200},
    ],
}


def main():
    ap = argparse.ArgumentParser(description="选题去重校验 —— 相似度分级比对")
    ap.add_argument("--input", help="输入 JSON（candidates/library）")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--demo", action="store_true", help="用内置样例跑一遍")
    a = ap.parse_args()

    payload = DEMO if a.demo else (at.read_json(a.input) if a.input else ap.error("需要 --input 或 --demo"))
    r = build(payload, a.outdir)
    s = r["summary"]
    print(f"候选 {s['候选数']} 条：重复 {s['重复']} / 相似可重做 {s['相似(可重做)']} / 通过 {s['通过']}")
    for f in r["files"]:
        print(" 产物:", f)
    at.emit(r)


if __name__ == "__main__":
    main()
