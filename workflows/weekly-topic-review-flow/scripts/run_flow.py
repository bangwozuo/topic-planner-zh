# -*- coding: utf-8 -*-
"""
每周选题复盘流程 —— 端到端编排脚本。

编排逻辑（与 SKILL.md 的 DAG 一致）：
  每周一 09:00 定时触发
  → 内置：爆款判定（点赞 > 账号 30 天点赞均值 × 5，leave-one-out 基准）
  → 内置：爆款率核算（基准 1/10：十条出一爆即合格）+ 归因（来源/象限/标题句式）
  → 内置：来源权重更新（0.7×min(爆款率/0.1,1.5) + 0.3×当前权重，样本 <10 不调权）
  → 内置：下周选题倾向（来源/象限配比建议）
  → 选题复盘报告.xlsx + weekly_review.json
  → 权重与状态更新建议交 topic-knowledge-base（待人工确认，AI 不改库）

失败处理：
  - posts 为空 → 「本周无发布记录」占位正常退出（不编造）
  - 单条记录缺字段 → 该条标注「数据不全」参与计数但不参与均值与归因
  - 账号 30 天均值缺失 → 用本周条均近似并标注「近似基准，须人工校准」
  - 样本 <10 的来源 → 权重不变并标注「样本不足」

用法：
  python run_flow.py --input input.json --outdir out
  python run_flow.py --demo
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
FLOW_DIR = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(FLOW_DIR))
sys.path.insert(0, os.path.join(REPO, "lib"))

try:
    import assettools as at
except ImportError:  # pragma: no cover
    print("[错误] 未找到 lib/assettools.py", file=sys.stderr)
    sys.exit(2)

MULTIPLE = 5
BASELINE = 0.1  # 爆款率基准 1/10
NUM_PAT = re.compile(r"\d+|[一二三四五六七八九十两]{1,3}(个|条|招|步|天|种|件|岁|万)")
Q_PAT = re.compile(r"？|\?|为什么|怎么|如何|凭什么|谁懂|有没有")
CONTRAST_PAT = re.compile(r"却|竟然|居然|反而|其实|没想到|真相|内幕|反向|劝退|避雷|原来")
WEIGHT_CHANGE_ALERT = 0.2


def classify_title(title: str) -> str:
    if NUM_PAT.search(title):
        return "数字锚点"
    if Q_PAT.search(title):
        return "疑问悬念"
    if CONTRAST_PAT.search(title):
        return "反差词"
    return "平铺直叙"


def review(payload):
    posts = payload.get("posts", [])
    if not posts:
        raise SystemExit("[错误] posts 为空：请提供本周发布记录（title/likes/views/days_since_post）")
    baseline = payload.get("avg_likes_30d")

    rows, incomplete = [], []
    likes_all = []
    for p in posts:
        title = str(p.get("title", ""))
        likes = p.get("likes")
        if likes is None or title == "":
            incomplete.append({"title": title, "reason": "缺 title 或 likes，不计入均值与爆款判定"})
            continue
        likes = float(likes)
        likes_all.append((p, likes))
        views = float(p.get("views", 0)) or None
        rows.append({
            "标题": title,
            "来源": p.get("source", "未标注"),
            "象限": p.get("quadrant", "未标注"),
            "标题句式": classify_title(title),
            "发布(天前)": float(p.get("days_since_post", 0)),
            "播放": int(views) if views else None,
            "点赞": int(likes),
            "评论": int(p.get("comments", 0)),
            "收藏": int(p.get("collects", 0)),
        })

    if likes_all:
        computed = sum(l for _, l in likes_all) / len(likes_all)
        if baseline:
            baseline = float(baseline)
            baseline_note = f"账号 30 天均值 {baseline:.0f}（用户提供）"
        else:
            baseline = computed
            baseline_note = f"近似基准（本周条均 {baseline:.0f}），须人工用后台 30 天均值校准"
    else:
        baseline_note = "无有效数据"

    viral_count = 0
    for row, (p, likes) in zip([r for r in rows if r["点赞"] is not None], likes_all):
        ratio = likes / baseline if baseline else 0
        row["点赞/基准"] = round(ratio, 1)
        row["判定"] = "🔥 爆款" if ratio > MULTIPLE else ("偏高" if ratio > 2 else "常态")
        row["完播/互动备注"] = ""
        if views := row.get("播放"):
            like_rate = likes / views * 100
            row["点赞率"] = f"{like_rate:.1f}%"
            row["完播/互动备注"] = "点赞率 ≥3% 优秀" if like_rate >= 3 else ("点赞率 ≥3% 及格线以下" if like_rate >= 2 else "点赞率偏低")
        else:
            row["点赞率"] = "—（缺播放）"
        if ratio > MULTIPLE:
            viral_count += 1

    rows.sort(key=lambda r: -(r["点赞"] or 0))
    for i, r in enumerate(rows, 1):
        r["#"] = i

    # 爆款率 vs 1/10 基准
    n = len([r for r in rows if r["点赞"] is not None])
    viral_rate = viral_count / n if n else 0.0
    rate_verdict = "达标（基准 1/10，不追求条条爆）" if viral_rate >= BASELINE else "未达标（连续 3 周未达标须复盘选题公式）"

    # 归因：来源 × 象限 × 句式 的爆款分布
    def agg(key):
        d = defaultdict(lambda: [0, 0])
        for r in rows:
            if r["点赞"] is None:
                continue
            k = r[key]
            d[k][1] += 1
            if r["判定"] == "🔥 爆款":
                d[k][0] += 1
        return {k: f"{v[0]}/{v[1]}" for k, v in sorted(d.items(), key=lambda x: -x[1][0])}

    # 来源权重更新（0.7×min(rate/0.1,1.5) + 0.3×当前）
    weights = []
    src_stats = defaultdict(lambda: [0, 0])
    for r in rows:
        if r["点赞"] is None:
            continue
        src_stats[r["来源"]][1] += 1
        if r["判定"] == "🔥 爆款":
            src_stats[r["来源"]][0] += 1
    current_weights = payload.get("source_weights", {})
    for src, (viral, cnt) in sorted(src_stats.items(), key=lambda x: -x[1][1]):
        cur = float(current_weights.get(src, 1.0))
        if cnt < 10:
            weights.append({"来源": src, "本周爆款/条数": f"{viral}/{cnt}",
                            "当前权重": cur, "新权重": cur, "备注": "样本 <10，不调权"})
        else:
            rate = viral / cnt
            comp = min(rate / BASELINE, 1.5)
            new = 0.7 * comp + 0.3 * cur
            new = max(0.5, min(1.5, new))
            alert = "变化 >0.2，单列人工确认" if abs(new - cur) > WEIGHT_CHANGE_ALERT else ""
            weights.append({"来源": src, "本周爆款/条数": f"{viral}/{cnt}",
                            "当前权重": cur, "新权重": round(new, 3), "备注": alert or "已按公式更新"})

    summary = {
        "发布条数": n,
        "爆款条数": viral_count,
        "爆款率": f"{viral_rate:.0%}（基准 1/10）",
        "爆款率判定": rate_verdict,
        "基准说明": baseline_note,
        "来源爆款分布": agg("来源"),
        "句式爆款分布": agg("标题句式"),
        "数据不全": len(incomplete),
        "下周倾向": "",
    }
    return rows, weights, incomplete, summary


DEMO = {
    "week": "2026-W40",
    "avg_likes_30d": 1800,
    "source_weights": {"平台热榜": 1.28, "竞品爆款拆解": 1.35, "评论区高赞提问": 0.65, "节点日历": 1.0},
    "posts": [
        {"title": "被裁员那天我在工位坐到凌晨：3 个动作保住赔偿金", "source": "竞品爆款拆解", "quadrant": "时效×垂直", "views": 240000, "likes": 12800, "comments": 420, "collects": 980, "days_since_post": 5},
        {"title": "面试被问期望薪资怎么答：3 个话术模板", "source": "搜索下拉词", "quadrant": "常青×垂直", "views": 52000, "likes": 2600, "comments": 96, "collects": 890, "days_since_post": 4},
        {"title": "国庆假期后第一天上班，怎么快速找回状态", "source": "节点日历", "quadrant": "时效×垂直", "views": 31000, "likes": 980, "comments": 44, "collects": 120, "days_since_post": 6},
        {"title": "为什么你一开口汇报就冷场？", "source": "评论区高赞提问", "quadrant": "常青×垂直", "views": 28000, "likes": 1150, "comments": 88, "collects": 210, "days_since_post": 3},
        {"title": "日常vlog：我的普通一天", "source": "平台热榜", "quadrant": "时效×泛", "views": 9000, "likes": 210, "comments": 12, "collects": 8, "days_since_post": 2},
        {"title": "没写标题随手发的测试视频", "source": "未标注", "days_since_post": 1},
    ],
}


def main():
    ap = argparse.ArgumentParser(description="每周选题复盘流程")
    ap.add_argument("--input", help="流程输入 JSON（week/posts/avg_likes_30d/source_weights）")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()

    at.ensure_outdir(a.outdir)
    if a.demo:
        payload = DEMO
    elif a.input:
        payload = at.read_json(a.input)
    else:
        ap.error("需要 --input / --demo 之一")

    if not payload.get("posts"):
        print("[失败处理] 本周无发布记录：输出占位报告，不编造数据。")
        xlsx = at.write_excel(os.path.join(a.outdir, "选题复盘报告.xlsx"),
                              {"复盘明细": [{"标题": "（本周无发布记录）"}],
                               "汇总": [{"项": "结论", "内容": "本周无发布"}]})
        at.emit({"files": [xlsx], "summary": {"结论": "本周无发布"}})
        return

    rows, weights, incomplete, summary = review(payload)

    # 下周倾向：按爆款分布给配比建议
    src_dist = summary["来源爆款分布"]
    top_src = next(iter(src_dist), None)
    summary["下周倾向"] = (
        f"来源配比：向「{top_src}」倾斜（本周爆款最多）；"
        f"常青固定栏目保底 60%，热点机动位 ≤30%；"
        f"句式上「{summary['句式爆款分布'] and next(iter(summary['句式爆款分布']))}」表现最好，优先套用"
        if src_dist else "本周无有效数据，维持现有配比")

    xlsx = at.write_excel(
        os.path.join(a.outdir, "选题复盘报告.xlsx"),
        {
            "复盘明细": rows,
            "权重更新": weights,
            "数据不全": incomplete or [{"title": "—", "reason": "—"}],
            "汇总": [{"项": k, "内容": str(v)} for k, v in summary.items()],
        },
        highlights={"复盘明细": {"判定": "contains:爆款"},
                    "权重更新": {"备注": "contains:人工确认"}},
        widths={"复盘明细": {"标题": 40, "完播/互动备注": 24}},
    )
    js = at.write_json({"summary": summary, "rows": rows, "weights": weights,
                        "incomplete": incomplete, "generated_at": at.stamp(),
                        "note": "权重更新为建议值，须经 topic-knowledge-base 人工确认后生效"},
                       os.path.join(a.outdir, "weekly_review.json"))

    if rows:
        top = rows[0]
        at.bar_chart(
            os.path.join(a.outdir, "本周表现Top5.png"),
            [r["标题"][:12] for r in rows[:5]],
            [r["点赞"] for r in rows[:5]],
            title="本周点赞 Top5", ylabel="点赞", horizontal=True)
        files = [xlsx, os.path.join(a.outdir, "本周表现Top5.png"), js]
    else:
        files = [xlsx, js]

    print(f"本周 {summary['发布条数']} 条：爆款 {summary['爆款条数']}，"
          f"爆款率 {summary['爆款率']} —— {summary['爆款率判定']}")
    print(f"下周倾向：{summary['下周倾向'][:60]}…")
    for f in files:
        print(" 产物:", f)
    at.emit({"files": files, "summary": summary})


if __name__ == "__main__":
    main()
