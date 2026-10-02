# -*- coding: utf-8 -*-
"""
全平台热点雷达 —— 热榜候选池聚合与时效扫描器。

职责边界：本脚本只做**确定性计算与产物生成**（跨平台去重、热度归一化、
时效衰减、赛道标记、排序出表）。条目是否值得追、蹭法是否安全、赛道匹配
怎么标定，由模型按 prompt.txt 完成（模型的强项）。

核心规则（与 prompt.txt 一致）：
  - 热梗半衰期 48h：发布超 48h 的热点按半衰模型衰减，超 168h（7 天）直接淘汰
  - 跨平台重合：同一话题被 ≥2 个平台收录 = 真热点，热度分上浮 10%
  - 热度归一：各平台热度口径不同（抖音赞/微博转发/知乎浏览），取 log10 后
    min-max 归一化到 0-100，避免被单平台爆款压扁
  - 赛道标记：命中垂直赛道词表记「垂直」，供下游按选题四象限分类

用法：
  python radar_scan.py --input input.json --outdir out
  python radar_scan.py --demo                 # 用内置样例跑一遍
  python radar_scan.py --text "标题" --platform 抖音 --heat 50000

产物：
  out/热点候选池.xlsx   候选明细 / 平台分布 / 汇总 三 sheet
  out/热点平台分布.png  各平台入选条数柱状图
  out/radar_scan.json   机器可读结果（供 hotspot-aggregate-scan-flow 读取）
"""
from __future__ import annotations

import argparse
import math
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

HALF_LIFE_H = 48      # 热梗半衰期 48h
MAX_AGE_H = 168       # 超 7 天淘汰
CROSS_BONUS = 1.10    # 跨平台重合上浮 10%

# 垂直赛道词表（按账号定位启用；demo 以「职场成长/自媒体运营」赛道为例）
VERTICAL_WORDS = [
    r"副业|自媒体|涨粉|流量|账号|变现|接单|私域|小红书|抖音|公众号|选题|脚本|拍摄|剪辑",
    r"职场|面试|简历|加班|裸辞|跳槽|工资|裁员|副业刚需|下班后|搞钱",
]

# 灾难/事故类：只标记不删除（删不删由人工确认，脚本只给红线提示）
RISK_WORDS = r"地震|火灾|爆炸|坠楼|车祸|空难|洪灾|疫情|死亡|遇难|自杀|诈骗|拐卖"


_PUNCT = re.compile("[\\s，。：:；;、！!？?「」『』“”‘’·,.\\-—|]")

def _similarity(a: str, b: str) -> float:
    """去标点后的字符二元组相似度：Jaccard 与包含度取大者，用于跨平台同话题合并。

    只用 Jaccard 会漏掉「长标题 vs 短标题改写」（如抖音长句 vs 小红书短句），
    所以补一个包含度 = 公共二元组 / 较短一方的二元组数。
    """
    a, b = _PUNCT.sub("", a), _PUNCT.sub("", b)
    sa = {a[i:i + 2] for i in range(len(a) - 1)} if len(a) > 1 else {a}
    sb = {b[i:i + 2] for i in range(len(b) - 1)} if len(b) > 1 else {b}
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    jaccard = inter / len(sa | sb)
    contain = inter / min(len(sa), len(sb))
    return max(jaccard, contain)


def _norm_heat(vals):
    """各平台热度口径不同，log10 归一化避免极值压扁。"""
    logs = [math.log10(max(v, 1)) for v in vals]
    lo, hi = min(logs), max(logs)
    if hi == lo:
        return [50.0] * len(vals)
    return [round((v - lo) / (hi - lo) * 100, 1) for v in logs]


def scan(payload):
    entries = payload.get("entries", [])
    if not entries:
        raise SystemExit("[错误] entries 为空：请提供热榜条目（title/platform/heat/hours_since）")
    heats = _norm_heat([e.get("heat", 0) for e in entries])

    # 第一步：跨平台同话题合并（相似度 ≥0.55 视为同一话题）
    topics = []  # each: {"title": 最早出现的标题, "platforms": [...], "max_heat_norm": f}
    for e, h in sorted(zip(entries, heats), key=lambda x: -x[1]):
        merged = False
        for t in topics:
            if _similarity(e.get("title", ""), t["title"]) >= 0.55:
                t["platforms"].append(e.get("platform", ""))
                t["heat_norm"] = max(t["heat_norm"], h)
                t["hours_since"] = min(t["hours_since"], e.get("hours_since", 0))
                merged = True
                break
        if not merged:
            topics.append({"title": e.get("title", ""), "platforms": [e.get("platform", "")],
                           "heat_norm": h, "hours_since": e.get("hours_since", 0),
                           "rank": e.get("rank", "")})

    # 第二步：赛道标记 + 时效衰减 + 风险标记
    rows = []
    for t in topics:
        title = t["title"]
        n_plat = len(set(t["platforms"]))
        vertical = bool(re.search("|".join(VERTICAL_WORDS), title))
        risk = bool(re.search(RISK_WORDS, title))
        age = t["hours_since"]
        heat = round(t["heat_norm"] * (CROSS_BONUS if n_plat >= 2 else 1.0), 1)
        decay = round(0.6 + 0.4 * (0.5 ** (age / HALF_LIFE_H)), 3)
        score = round(heat * decay, 1)

        if age > MAX_AGE_H:
            level, note = "C 淘汰", "超 7 天，热度已过半衰窗口"
        elif risk:
            level, note = "R 红线", "灾难/事故类热点：不蹭（合规红线），仅做无关内容排查"
        elif vertical and age <= 24:
            level, note = "A 追", "时效×垂直=爆款区，24h 内出稿抢占先机"
        elif vertical and age <= 48:
            level, note = "A 追", "时效×垂直，48h 内出稿仍有效"
        elif n_plat >= 2:
            level, note = "B 观察", f"跨 {n_plat} 平台重合，但非本赛道，看能否切垂直角度"
        elif age <= 48:
            level, note = "B 观察", "单平台热度，次日复查是否跨平台扩散"
        else:
            level, note = "C 淘汰", "超 48h 且未跨平台扩散，半衰已过"

        # A 级热度过低降级：垂直但热度垫底的题不值得优先投入
        if level == "A 追" and score < 25:
            level, note = "B 观察", "赛道垂直但热度过低（归一后 <25），降级观察"

        rows.append({
            "热点标题": title,
            "收录平台": "、".join(sorted(set(t["platforms"]))),
            "平台数": n_plat,
            "热度分(归一)": heat,
            "时效系数": decay,
            "距首发(h)": age,
            "赛道": "垂直" if vertical else "泛",
            "得分": score,
            "级别": level,
            "备注": note,
        })
    rows.sort(key=lambda r: -r["得分"])
    for i, r in enumerate(rows, 1):
        r["#"] = i

    # 平台分布（入池条数口径）
    plat_dist = {}
    for e in entries:
        plat_dist[e.get("platform", "未知")] = plat_dist.get(e.get("platform", "未知"), 0) + 1

    summary = {
        "采集日期": payload.get("date", at.stamp()[:10]),
        "原始条目": len(entries),
        "合并后话题": len(rows),
        "A级(追)": sum(1 for r in rows if r["级别"] == "A 追"),
        "B级(观察)": sum(1 for r in rows if r["级别"] == "B 观察"),
        "C级(淘汰)": sum(1 for r in rows if r["级别"].startswith("C")),
        "红线标记": sum(1 for r in rows if r["级别"] == "R 红线"),
        "平台分布": "；".join(f"{k} {v} 条" for k, v in sorted(plat_dist.items(), key=lambda x: -x[1])),
    }
    return rows, summary, plat_dist


def build(payload, outdir):
    rows, summary, plat_dist = scan(payload)
    at.ensure_outdir(outdir)

    xlsx = at.write_excel(
        os.path.join(outdir, "热点候选池.xlsx"),
        {
            "候选池": rows or [{"热点标题": "（今日无有效热点）"}],
            "平台分布": [{"平台": k, "原始条数": v} for k, v in
                        sorted(plat_dist.items(), key=lambda x: -x[1])],
            "汇总": [{"项": k, "内容": str(v)} for k, v in summary.items()],
        },
        highlights={"候选池": {"级别": "contains:A 追"}},
        widths={"候选池": {"热点标题": 42, "收录平台": 18, "备注": 34}},
    )
    labels = [k for k in plat_dist]
    png = at.bar_chart(
        os.path.join(outdir, "热点平台分布.png"),
        labels, [plat_dist[k] for k in labels],
        title="各平台采集条数", ylabel="条数")
    js = at.write_json({"summary": summary, "rows": rows,
                        "rules": "半衰48h；跨平台上浮10%；A=时效×垂直；灾难类标红线",
                        "generated_at": at.stamp(),
                        "note": "机器聚合结果；赛道匹配标定与蹭法安全性须由模型按 prompt.txt 复核"},
                       os.path.join(outdir, "radar_scan.json"))
    return {"files": [xlsx, png, js], "summary": summary, "rows": rows}


DEMO = {
    "date": "2026-09-30",
    "entries": [
        {"title": "00后整顿职场：拒绝无效加班从这3句话开始", "platform": "抖音", "heat": 1860000, "rank": 2, "hours_since": 9},
        {"title": "00后整顿职场，拒绝无效加班的3句话", "platform": "小红书", "heat": 92000, "rank": 5, "hours_since": 14},
        {"title": "离职同事饭局上说的真话，句句戳心", "platform": "微博", "heat": 430000, "rank": 8, "hours_since": 26},
        {"title": "普通人搞钱副业：下班后2小时的3种变现路径", "platform": "小红书", "heat": 65000, "rank": 11, "hours_since": 6},
        {"title": "某地突发地震，多地震感明显", "platform": "微博", "heat": 2100000, "rank": 1, "hours_since": 3},
        {"title": "国庆自驾游避堵攻略，这5条路线亲测", "platform": "抖音", "heat": 760000, "rank": 4, "hours_since": 30},
        {"title": "国庆自驾避堵的5条路线", "platform": "知乎", "heat": 51000, "rank": 7, "hours_since": 40},
        {"title": "AI剪辑工具横评：剪映映美vs必剪谁更强", "platform": "抖音", "heat": 210000, "rank": 9, "hours_since": 60},
        {"title": "9.9元包邮的真相：电商低价内幕", "platform": "微博", "heat": 380000, "rank": 6, "hours_since": 120},
        {"title": "面试官最后问「你有什么问题吗」怎么答", "platform": "小红书", "heat": 48000, "rank": 15, "hours_since": 20},
        {"title": "地铁新线路今日开通", "platform": "微博", "heat": 150000, "rank": 13, "hours_since": 5},
        {"title": "前同事裁员的那个下午，我在工位学到的3件事", "platform": "知乎", "heat": 22000, "rank": 19, "hours_since": 200},
    ],
}


def main():
    ap = argparse.ArgumentParser(description="全平台热点雷达 —— 热榜聚合与时效扫描")
    ap.add_argument("--input", help="输入 JSON（date/entries）")
    ap.add_argument("--text", help="单条标题（快速测试）")
    ap.add_argument("--platform", default="通用")
    ap.add_argument("--heat", type=float, default=10000)
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--demo", action="store_true", help="用内置样例跑一遍")
    a = ap.parse_args()

    if a.demo:
        payload = DEMO
    elif a.input:
        payload = at.read_json(a.input)
    elif a.text:
        payload = {"entries": [{"title": a.text, "platform": a.platform,
                                "heat": a.heat, "hours_since": 0}]}
    else:
        ap.error("需要 --input / --text / --demo 之一")

    r = build(payload, a.outdir)
    s = r["summary"]
    print(f"原始 {s['原始条目']} 条 → 合并 {s['合并后话题']} 个话题："
          f"A 级 {s['A级(追)']} / B 级 {s['B级(观察)']} / C 级 {s['C级(淘汰)']} / 红线 {s['红线标记']}")
    for f in r["files"]:
        print(" 产物:", f)
    at.emit(r)


if __name__ == "__main__":
    main()
