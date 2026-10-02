# -*- coding: utf-8 -*-
"""
热点聚合扫描流程 —— 端到端编排脚本。

编排逻辑（与 SKILL.md 的 DAG 一致）：
  每日 07:30 定时触发
  → [hot-topic-radar] 五平台热榜聚合：跨平台合并 + 半衰衰减 + 四象限初判
  → [competitor-track] 竞品爆款扫描：5 倍均值判定 + 断更预警
  → 内置：候选池合并（雷达 A/B 级 ∪ 竞品爆款衍生角度）→ 每日候选池.xlsx

失败处理：
  - 上游脚本退出码 != 0 → 中止并打印 stderr（不静默失败）
  - 上游 JSON 产物缺失/损坏 → 中止并提示重跑上游
  - 热榜为空但竞品有数据 → 降级为「纯竞品日」正常完成
  - 竞品为空但热榜有数据 → 降级为「纯热点日」正常完成
  - 两者皆空 → 「今日无输入」占位清单正常退出（不编造）

用法：
  python run_flow.py --input input.json --outdir out
  python run_flow.py --demo
"""
from __future__ import annotations

import argparse
import json
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

RADAR_SCRIPT = os.path.join(REPO, "skills", "hot-topic-radar", "scripts", "radar_scan.py")
COMP_SCRIPT = os.path.join(REPO, "skills", "competitor-track", "scripts", "competitor_track.py")


def run_step(name: str, script: str, payload: dict, outdir: str, json_name: str) -> dict:
    """运行一个上游技能脚本，校验退出码与产物，返回其 JSON 结果。"""
    payload_path = os.path.join(outdir, f"_step_{name}_input.json")
    at.write_json(payload, payload_path)
    r = subprocess.run(
        [sys.executable, script, "--input", payload_path, "--outdir", outdir],
        cwd=FLOW_DIR, capture_output=True, text=True, timeout=180,
    )
    if r.returncode != 0:
        print(f"[失败处理] 上游技能 {name} 退出码 {r.returncode}，流程中止。", file=sys.stderr)
        print(r.stderr[-800:], file=sys.stderr)
        sys.exit(1)
    js = os.path.join(outdir, json_name)
    if not os.path.exists(js):
        print(f"[失败处理] 上游产物 {js} 缺失，流程中止（请重跑上游技能）。", file=sys.stderr)
        sys.exit(1)
    return at.read_json(js)


def merge(radar: dict, comp: dict) -> tuple[list, list, dict]:
    """内置步骤：热点候选与竞品情报合并为每日候选池。"""
    pool = []
    for row in radar.get("rows", []):
        if row["级别"] in ("A 追", "B 观察") and row["级别"] != "R 红线":
            pool.append({
                "类型": "热点（雷达）",
                "条目": row["热点标题"],
                "得分": row["得分"],
                "级别": row["级别"],
                "建议": row["备注"],
            })
    for row in comp.get("rows", []):
        if row["判定"] == "🔥 爆款":
            pool.append({
                "类型": "竞品爆款衍生",
                "条目": f"拆句式：{row['标题']}",
                "得分": row["倍数"],
                "级别": f"爆款 {row['倍数']}x",
                "建议": f"句式「{row['标题句式']}」可迁移，禁止照搬选题",
            })
    pool.sort(key=lambda r: -float(r["得分"]))
    for i, r in enumerate(pool, 1):
        r["#"] = i

    alerts = []
    for o in comp.get("overviews", []):
        if o["状态"] != "正常":
            alerts.append(f"{o['账号']}：{o['状态']}（最近更新 {o['最近更新(天前)']:.0f} 天前），建议换对标")

    summary = {
        "雷达热点": radar.get("summary", {}),
        "竞品爆款条数": comp.get("summary", {}).get("爆款条数", 0),
        "断更预警": "；".join(alerts) or "无",
        "候选池条数": len(pool),
        "今日建议": "；".join(r["条目"] for r in pool[:3]) if pool else "今日无候选，建议人工刷榜补充",
    }
    return pool, alerts, summary


DEMO = {
    "date": "2026-09-30",
    "niche": "职场成长/自媒体运营",
    "hotlist": {
        "date": "2026-09-30",
        "entries": [
            {"title": "00后整顿职场：拒绝无效加班从这3句话开始", "platform": "抖音", "heat": 1860000, "rank": 2, "hours_since": 9},
            {"title": "00后整顿职场，拒绝无效加班的3句话", "platform": "小红书", "heat": 92000, "rank": 5, "hours_since": 14},
            {"title": "某地突发地震，多地震感明显", "platform": "微博", "heat": 2100000, "rank": 1, "hours_since": 3},
            {"title": "普通人搞钱副业：下班后2小时的3种变现路径", "platform": "小红书", "heat": 65000, "rank": 11, "hours_since": 6},
            {"title": "面试官最后问「你有什么问题吗」怎么答", "platform": "小红书", "heat": 48000, "rank": 15, "hours_since": 20},
            {"title": "前同事裁员的那个下午，我在工位学到的3件事", "platform": "知乎", "heat": 22000, "rank": 19, "hours_since": 200},
        ],
    },
    "competitors": {
        "niche": "职场成长/自媒体运营",
        "posts": [
            {"account": "职场老张", "platform": "抖音", "title": "被裁员那天我在工位坐到凌晨：3 个动作保住赔偿金", "likes": 41000, "comments": 860, "shares": 1200, "days_ago": 6},
            {"account": "职场老张", "platform": "抖音", "title": "面试反问环节的 3 个加分问题", "likes": 5200, "comments": 140, "shares": 90, "days_ago": 11},
            {"account": "小鱼搞钱日记", "platform": "小红书", "title": "下班后搞副业 3 个月，收入从 0 到 8000 的路径", "likes": 12500, "comments": 340, "shares": 890, "days_ago": 4},
            {"account": "小鱼搞钱日记", "platform": "小红书", "title": "副业接单避雷：这 3 种单子千万别接", "likes": 2100, "comments": 76, "shares": 150, "days_ago": 9},
            {"account": "运营小笔记", "platform": "公众号", "title": "私域涨粉的 4 个抓手", "likes": 760, "comments": 32, "shares": 88, "days_ago": 21},
        ],
    },
}


def main():
    ap = argparse.ArgumentParser(description="热点聚合扫描流程")
    ap.add_argument("--input", help="流程输入 JSON（date/niche/hotlist/competitors）")
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

    hotlist = payload.get("hotlist") or {}
    competitors = payload.get("competitors") or {}

    # 空输入判定：两者皆空 → 占位清单正常退出
    if not hotlist.get("entries") and not competitors.get("posts"):
        print("[失败处理] 热榜与竞品输入均为空：输出占位清单，不编造数据。")
        xlsx = at.write_excel(
            os.path.join(a.outdir, "每日候选池.xlsx"),
            {"候选池": [{"条目": "（今日无输入：请补粘贴热榜或竞品数据）"}],
             "汇总": [{"项": "结论", "内容": "今日无输入"}]},
        )
        at.emit({"files": [xlsx], "summary": {"结论": "今日无输入"}})
        return

    # 步骤 1：雷达（热榜为空时降级：空热点清单）
    if hotlist.get("entries"):
        radar = run_step("radar", RADAR_SCRIPT, hotlist, a.outdir, "radar_scan.json")
    else:
        print("[失败处理] 热榜为空 → 降级为「纯竞品日」。")
        radar = {"rows": [], "summary": {"原始条目": 0, "合并后话题": 0, "A级(追)": 0, "B级(观察)": 0, "C级(淘汰)": 0, "红线标记": 0}}

    # 步骤 2：竞品（竞品为空时降级：空竞品清单）
    if competitors.get("posts"):
        comp = run_step("comp", COMP_SCRIPT, competitors, a.outdir, "competitor_track.json")
    else:
        print("[失败处理] 竞品为空 → 降级为「纯热点日」。")
        comp = {"rows": [], "overviews": [], "summary": {"爆款条数": 0, "追踪账号数": 0}}

    # 步骤 3（内置）：合并候选池
    pool, alerts, summary = merge(radar, comp)

    xlsx = at.write_excel(
        os.path.join(a.outdir, "每日候选池.xlsx"),
        {
            "候选池": pool or [{"条目": "（今日无候选）"}],
            "对标预警": [{"预警": t} for t in alerts] or [{"预警": "无"}],
            "汇总": [{"项": k, "内容": str(v)} for k, v in summary.items()],
        },
        highlights={"候选池": {"级别": "contains:A 追"},
                    "对标预警": {"预警": "contains:断更"}},
        widths={"候选池": {"条目": 44, "建议": 40}},
    )
    js = at.write_json({"summary": summary, "pool": pool, "alerts": alerts,
                        "generated_at": at.stamp(),
                        "note": "候选池由上游 radar_scan.json 与 competitor_track.json 合并，未新增数据"},
                       os.path.join(a.outdir, "daily_pool.json"))
    print(f"步骤 1  hot-topic-radar      ✅  → {a.outdir}/radar_scan.json")
    print(f"步骤 2  competitor-track     ✅  → {a.outdir}/competitor_track.json")
    print(f"步骤 3  合并候选池            ✅  → {xlsx}")
    print(f"汇总    候选 {len(pool)} 条；今日建议：{summary['今日建议']}")
    at.emit({"files": [xlsx, js], "summary": summary})


if __name__ == "__main__":
    main()
