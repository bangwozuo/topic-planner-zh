# -*- coding: utf-8 -*-
"""
竞品动态追踪 —— 竞品账号更新与爆款判定扫描器。

职责边界：本脚本只做**确定性计算与产物生成**（近 30 天互动均值、爆款判定、
更新节奏、标题句式统计）。账号值不值得对标、爆款标题该怎么学、抄到什么程度
算侵权，由模型按 prompt.txt 完成（模型的强项）。

核心规则（与 prompt.txt 一致）：
  - 爆款判定：单条点赞 > 该账号近 30 天点赞均值 × 5 = 爆款
  - 更新节奏：条/周 = 近 30 天条数 ÷ 4.3，连续 ≥14 天不更新 = 断更预警
  - 标题句式统计：数字锚点 / 疑问悬念 / 反差词命中比例，供拆解借鉴

用法：
  python competitor_track.py --input input.json --outdir out
  python competitor_track.py --demo                # 用内置样例跑一遍

产物：
  out/竞品追踪报告.xlsx   爆款明细 / 账号概览 / 汇总 三 sheet（爆款行标红）
  out/竞品互动对比.png    各账号近 30 天条均点赞柱状图
  out/competitor_track.json  机器可读结果（供 hotspot-aggregate-scan-flow 读取）
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

MULTIPLE = 5          # 爆款倍数：点赞 > 30 天均值 × 5
WEEKS = 4.3           # 30 天 ≈ 4.3 周
STALE_DAYS = 14       # 连续 ≥14 天无更新 = 断更预警
WINDOW_DAYS = 30      # 统计窗口

# 标题句式词表（统计口径，非评判）
NUM_PAT = re.compile(r"\d+|[一二三四五六七八九十两]{1,3}(个|条|招|步|天|种|件|岁|万)")
Q_PAT = re.compile(r"？|\?|为什么|怎么|如何|凭什么|谁懂|有没有")
CONTRAST_PAT = re.compile(r"却|竟然|居然|反而|其实|没想到|真相|内幕|反向|劝退|避雷|原来")
DAYS_PAT = re.compile(r"(\d+(?:\.\d+)?)\s*天前")


def _days_ago(item, default):
    m = DAYS_PAT.search(str(item.get("days_ago", default)))
    if m:
        return float(m.group(1))
    v = item.get("days_ago", default)
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def analyze(payload):
    posts = payload.get("posts", [])
    if not posts:
        raise SystemExit("[错误] posts 为空：请提供竞品帖子（account/platform/title/likes/days_ago）")

    # 近 30 天均值按账号分桶
    stats = {}   # account -> list[post]
    for p in posts:
        acc = p.get("account", "未知账号")
        stats.setdefault(acc, []).append(p)

    rows, overviews = [], []
    for acc, plist in stats.items():
        recent = [p for p in plist if _days_ago(p, 0) <= WINDOW_DAYS]
        if not recent:
            recent = plist  # 全部超出窗口时退化为全量，并标注
        likes = [float(p.get("likes", 0)) for p in recent]
        avg = sum(likes) / len(likes) if likes else 0.0
        for p in recent:
            lk = float(p.get("likes", 0))
            # 均值基准用 leave-one-out：爆款会抬高整体均值，把自己算进基准里
            # 会自我稀释（41000 的爆款让均值变 12280，自己只剩 3.3 倍）。
            others = [v for v in likes if v != lk or likes.count(v) > 1]
            # 更稳妥：按"去掉当前这条"的位置法重算
            idx_all = [i for i, p2 in enumerate(recent) if p2 is not p]
            base = (sum(float(recent[i].get("likes", 0)) for i in idx_all) / len(idx_all)) if idx_all else 0.0
            is_viral = base > 0 and lk > base * MULTIPLE
            days = _days_ago(p, 0)
            title = str(p.get("title", ""))
            marks = []
            if NUM_PAT.search(title):
                marks.append("数字锚点")
            if Q_PAT.search(title):
                marks.append("疑问悬念")
            if CONTRAST_PAT.search(title):
                marks.append("反差词")
            rows.append({
                "账号": acc,
                "平台": p.get("platform", ""),
                "标题": title,
                "点赞": int(lk),
                "评论": int(p.get("comments", 0)),
                "收藏/转发": int(p.get("shares", 0)),
                "距今天(天)": days,
                "基准均值(去本条)": round(base, 1),
                "倍数": round(lk / base, 1) if base > 0 else 0.0,
                "判定": "🔥 爆款" if is_viral else ("偏高" if base > 0 and lk > base * 2 else "常态"),
                "标题句式": "、".join(marks) if marks else "平铺直叙",
            })
        days_list = sorted(_days_ago(p, 0) for p in recent)
        gap = days_list[0] if days_list else None  # 距今最近一条
        stale = gap is not None and gap >= STALE_DAYS
        # 最高倍数同样用 leave-one-out 口径，与明细行一致
        ratios = []
        for i, p in enumerate(recent):
            others = [float(q.get("likes", 0)) for j, q in enumerate(recent) if j != i]
            b = sum(others) / len(others) if others else 0.0
            if b > 0:
                ratios.append(float(p.get("likes", 0)) / b)
        overviews.append({
            "账号": acc,
            "平台": recent[0].get("platform", "") if recent else "",
            "近30天条数": len(recent),
            "更新节奏(条/周)": round(len(recent) / WEEKS, 1),
            "30天条均点赞": round(avg, 1),
            "条均评论": round(sum(float(p.get("comments", 0)) for p in recent) / len(recent), 1) if recent else 0,
            "最高倍数": round(max(ratios, default=0), 1),
            "最近更新(天前)": gap,
            "状态": "⚠ 断更预警" if stale else "正常",
        })

    rows.sort(key=lambda r: -(r["点赞"]))
    for i, r in enumerate(rows, 1):
        r["#"] = i
    overviews.sort(key=lambda o: -o["30天条均点赞"])

    n_viral = sum(1 for r in rows if r["判定"] == "🔥 爆款")
    summary = {
        "追踪账号数": len(overviews),
        "近30天帖子总数": len(rows),
        "爆款条数": n_viral,
        "爆款判定规则": f"点赞 > 该账号 30 天均值 × {MULTIPLE}",
        "断更预警": "；".join(o["账号"] for o in overviews if o["状态"] != "正常") or "无",
        "条均点赞最高": f"{overviews[0]['账号']}（{overviews[0]['30天条均点赞']}）" if overviews else "",
        "账号定位": payload.get("niche", ""),
    }
    return rows, overviews, summary


def build(payload, outdir):
    rows, overviews, summary = analyze(payload)
    at.ensure_outdir(outdir)

    xlsx = at.write_excel(
        os.path.join(outdir, "竞品追踪报告.xlsx"),
        {
            "爆款明细": rows or [{"账号": "（无数据）"}],
            "账号概览": overviews or [{"账号": "（无数据）"}],
            "汇总": [{"项": k, "内容": str(v)} for k, v in summary.items()],
        },
        highlights={"爆款明细": {"判定": "contains:爆款"},
                    "账号概览": {"状态": "contains:断更"}},
        widths={"爆款明细": {"标题": 44, "标题句式": 20},
                "账号概览": {"账号": 22}},
    )
    png = at.bar_chart(
        os.path.join(outdir, "竞品互动对比.png"),
        [o["账号"][:12] for o in overviews],
        [o["30天条均点赞"] for o in overviews],
        title="竞品近 30 天条均点赞对比", ylabel="条均点赞", horizontal=True)
    js = at.write_json({"summary": summary, "rows": rows, "overviews": overviews,
                        "rules": f"爆款=点赞>30天均值×{MULTIPLE}；断更=≥{STALE_DAYS}天无更新",
                        "generated_at": at.stamp(),
                        "note": "机器统计结果；对标策略与借鉴尺度须由模型按 prompt.txt 复核"},
                       os.path.join(outdir, "competitor_track.json"))
    return {"files": [xlsx, png, js], "summary": summary,
            "viral_count": summary["爆款条数"], "rows": rows, "overviews": overviews}


DEMO = {
    "niche": "职场成长/自媒体运营",
    "posts": [
        # 竞品 A：更新勤，有一条爆款（点赞 41000 vs 均值约 5000 → 8.2 倍）
        {"account": "职场老张", "platform": "抖音", "title": "被裁员那天我在工位坐到凌晨：3 个动作保住赔偿金", "likes": 41000, "comments": 860, "shares": 1200, "days_ago": 6},
        {"account": "职场老张", "platform": "抖音", "title": "面试反问环节的 3 个加分问题", "likes": 5200, "comments": 140, "shares": 90, "days_ago": 11},
        {"account": "职场老张", "platform": "抖音", "title": "为什么领导总让你口头汇报？", "likes": 6100, "comments": 210, "shares": 60, "days_ago": 17},
        {"account": "职场老张", "platform": "抖音", "title": "简历石沉大海的 5 个真相", "likes": 4300, "comments": 95, "shares": 45, "days_ago": 23},
        {"account": "职场老张", "platform": "抖音", "title": "年终述职PPT这样搭结构", "likes": 4800, "comments": 88, "shares": 120, "days_ago": 29},
        # 竞品 B：小红书图文号，有条均更高的小爆款
        {"account": "小鱼搞钱日记", "platform": "小红书", "title": "下班后搞副业 3 个月，收入从 0 到 8000 的路径", "likes": 12500, "comments": 340, "shares": 890, "days_ago": 4},
        {"account": "小鱼搞钱日记", "platform": "小红书", "title": "副业接单避雷：这 3 种单子千万别接", "likes": 2100, "comments": 76, "shares": 150, "days_ago": 9},
        {"account": "小鱼搞钱日记", "platform": "小红书", "title": "普通人的第一桶金其实不需要勇气", "likes": 1800, "comments": 55, "shares": 60, "days_ago": 16},
        {"account": "小鱼搞钱日记", "platform": "小红书", "title": "我删掉了 2000 粉丝", "likes": 950, "comments": 40, "shares": 12, "days_ago": 25},
        # 竞品 C：断更中
        {"account": "运营小笔记", "platform": "公众号", "title": "私域涨粉的 4 个抓手", "likes": 760, "comments": 32, "shares": 88, "days_ago": 21},
        {"account": "运营小笔记", "platform": "公众号", "title": "选题会怎么开才不冷场", "likes": 620, "comments": 18, "shares": 40, "days_ago": 34},
    ],
}


def main():
    ap = argparse.ArgumentParser(description="竞品动态追踪 —— 更新与爆款判定扫描")
    ap.add_argument("--input", help="输入 JSON（niche/posts）")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--demo", action="store_true", help="用内置样例跑一遍")
    a = ap.parse_args()

    payload = DEMO if a.demo else (at.read_json(a.input) if a.input else ap.error("需要 --input 或 --demo"))
    r = build(payload, a.outdir)
    s = r["summary"]
    print(f"追踪 {s['追踪账号数']} 个账号、近 30 天 {s['近30天帖子总数']} 条："
          f"爆款 {s['爆款条数']} 条；断更预警：{s['断更预警']}")
    for f in r["files"]:
        print(" 产物:", f)
    at.emit(r)


if __name__ == "__main__":
    main()
