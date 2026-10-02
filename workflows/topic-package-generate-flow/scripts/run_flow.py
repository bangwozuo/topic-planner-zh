# -*- coding: utf-8 -*-
"""
选题包生成流程 —— 端到端编排脚本。

编排逻辑（与 SKILL.md 的 DAG 一致）：
  WF2 去重后选题榜（dedup_match_result.json）或用户粘贴榜单
  → 内置：四象限归类（时效/常青 × 垂直/泛）+ 机动位配额检查（热点 ≤30% 条数）
  → 内置：每选题 3 标题锻造（按 viral-title-craft 六公式取 3 种，字数核对）
  → 内置：建议角度（按 viral-structure-decode 的钩子类型映射）
  → 选题包.xlsx（10 选题 × 角度 × 3 标题 × 受众）+ topic_package.json
  → 人工确认后进入内容日历（本流程不发布）

失败处理：
  - 输入缺失字段 → 用默认值并在备注标注，重要字段缺失跳过该条并列出
  - 候选为空 → 「今日无候选」占位正常退出（不硬凑 10 条）
  - 标题超平台字数上限 → 自动截断备选并标注「超限，须人工改写」
  - 热点机动位占比 >30% → 溢出的热点题降为「机动位候补」，不删除

用法：
  python run_flow.py --input input.json --outdir out
  python run_flow.py --demo
"""
from __future__ import annotations

import argparse
import os
import re
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

# 与 viral-title-craft 一致的平台字数上限
PLATFORM_LIMIT = {"小红书": 20, "抖音": 30, "公众号": 64, "B站": 80, "知乎": 64}
MOBILE_CAP = 0.30  # 热点机动位 ≤30% 条数，防止账号标签漂移

_PUNCT = re.compile("[\\s，。：:；;、！!？?「」『』“”‘’·,.\\-—|]")


def _core(title: str, n: int = 10) -> str:
    """取标题核心短语（去标点后前 n 字），用于标题模板填空。"""
    t = _PUNCT.sub("", title)
    return t[:n]


def _num_in(title: str, default=3) -> str:
    """取标题里第一个有意义的数字（跳过 0 开头的年份/代称，如「00后」）。"""
    for m in re.finditer(r"\d+", title):
        if int(m.group(0)) > 0:
            return m.group(0)
    return str(default)


def make_titles(title: str, platform: str, source: str) -> list:
    """按 viral-title-craft 六公式取 3 种（数字锚点/反差悬念/疑问钩子），
    模板化生成候选标题并核对字数。模板只到句式层，正文内容须人工补足。"""
    core = _core(title, 9)
    n = _num_in(title)
    templates = [
        ("数字锚点", f"{n} 个要点讲清{core}"),
        ("反差悬念", f"{core}的真相，和你想的相反"),
        ("疑问钩子", f"为什么{core}总做不对？"),
    ]
    limit = PLATFORM_LIMIT.get(platform, 30)
    out = []
    for formula, t in templates:
        over = len(t) > limit
        out.append({
            "标题": t + ("（超限待改写）" if over else ""),
            "字数": len(t),
            "公式": formula,
            "合规": "超平台上限，须人工改写" if over else "OK",
        })
    return out


ANGLE_MAP = {
    "平台热榜": "痛点瞬间角度：抓热点事件里普通人卡住的那一下",
    "竞品爆款拆解": "句式迁移角度：借结构不借内容，换自己的场景与数据",
    "评论区高赞提问": "原话作钩子角度：把高赞提问原文放进前 3 秒",
    "搜索下拉词": "搜索问答角度：标题即下拉词，正文直接回答",
    "节点日历": "提前备稿角度：节点前 7 天发布，抢搜索上升期",
}


def build_package(candidates: list, platform: str, total_slots: int):
    """内置步骤：四象限归类 + 3 标题 + 建议角度。"""
    rows, skipped = [], []
    hot_pool, ever_pool = [], []
    for c in candidates:
        title = c.get("title", "")
        if not title:
            skipped.append({"原因": "缺 title 字段", "条目": str(c)[:40]})
            continue
        evergreen = bool(c.get("evergreen", False))
        score = float(c.get("总分", c.get("score", 0)) or 0)
        quadrant = ("常青×垂直" if evergreen else "时效×垂直") if c.get("match", 0.9) >= 0.5 \
            else ("常青×泛" if evergreen else "时效×泛")
        source = c.get("来源", c.get("source", ""))
        row = {
            "选题": title,
            "来源": source,
            "评分": score,
            "象限": quadrant,
            "建议角度": ANGLE_MAP.get(source, "痛点瞬间角度：抓具体场景"),
            "目标受众": c.get("audience", "账号核心粉丝（垂直人群）"),
        }
        if quadrant in ("时效×垂直", "时效×泛"):
            hot_pool.append(row)
        elif quadrant == "常青×垂直":
            ever_pool.append(row)
        else:
            skipped.append({"原因": "常青×泛象限，无差异化不做", "条目": title})
    hot_pool.sort(key=lambda r: -r["评分"])
    ever_pool.sort(key=lambda r: -r["评分"])

    # 机动位配额：热点 ≤30%；超出降为候补（固定栏目以常青长尾为主）
    hot_cap = max(1, int(total_slots * MOBILE_CAP)) if total_slots else len(hot_pool)
    for i, row in enumerate(hot_pool):
        row["排期属性"] = "固定栏目（时效）" if i < hot_cap else "机动位候补（超 30% 配额）"
    for row in ever_pool:
        row["排期属性"] = "固定栏目（常青长尾）"

    ordered = ever_pool + hot_pool
    for i, row in enumerate(ordered, 1):
        row["#"] = i
        row["候选标题（3 公式）"] = "；".join(
            f"{t['标题']}[{t['公式']}·{t['字数']}字·{t['合规']}]"
            for t in make_titles(row["选题"], platform, row["来源"]))
        rows.append(row)

    summary = {
        "平台": platform,
        "候选数": len(candidates),
        "入包选题": len(rows),
        "跳过": len(skipped),
        "热点机动位": f"{min(len(hot_pool), hot_cap)}/{hot_cap}（上限 30%）",
        "常青固定栏目": len(ever_pool),
        "人工确认": "选题包仅草稿；标题须人工改写终稿后进入内容日历",
    }
    return rows, skipped, summary


DEMO = {
    "platform": "小红书",
    "total_slots": 10,
    "candidates": [
        {"title": "00后整顿职场：拒绝无效加班从这3句话开始", "来源": "平台热榜", "总分": 92.6, "match": 0.9, "hours_since": 9, "audience": "0-3 年职场新人"},
        {"title": "面试官最后问「你有什么问题吗」怎么答", "来源": "搜索下拉词", "总分": 92.5, "match": 0.95, "evergreen": True, "audience": "正在求职的人"},
        {"title": "被裁员那天我在工位坐到凌晨：3 个动作保住赔偿金", "来源": "竞品爆款拆解", "总分": 91.4, "match": 0.9, "hours_since": 30, "audience": "担心裁员的一线员工"},
        {"title": "国庆假期后第一天上班，怎么快速找回状态", "来源": "节点日历", "总分": 70.4, "match": 0.75, "hours_since": 2, "audience": "上班族"},
        {"title": "副业接单避雷：这 3 种单子千万别接", "来源": "评论区高赞提问", "总分": 88.0, "match": 0.9, "evergreen": True, "audience": "搞副业的新手"},
        {"title": "某个明星的演唱会造型解析", "来源": "平台热榜", "总分": 55.0, "match": 0.2, "hours_since": 5},
    ],
}


def main():
    ap = argparse.ArgumentParser(description="选题包生成流程")
    ap.add_argument("--input", help="流程输入 JSON（platform/total_slots/candidates）")
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

    candidates = payload.get("candidates", [])
    platform = payload.get("platform", "小红书")
    total_slots = int(payload.get("total_slots", 0) or 0)

    if not candidates:
        print("[失败处理] 候选为空：输出占位包，不硬凑 10 条。")
        xlsx = at.write_excel(os.path.join(a.outdir, "选题包.xlsx"),
                              {"选题包": [{"选题": "（今日无候选，请先跑 WF1/WF2）"}],
                               "汇总": [{"项": "结论", "内容": "今日无候选"}]})
        at.emit({"files": [xlsx], "summary": {"结论": "今日无候选"}})
        return

    rows, skipped, summary = build_package(candidates, platform, total_slots)

    xlsx = at.write_excel(
        os.path.join(a.outdir, "选题包.xlsx"),
        {
            "选题包": rows or [{"选题": "（无入选选题）"}],
            "跳过说明": skipped or [{"原因": "—", "条目": "—"}],
            "汇总": [{"项": k, "内容": str(v)} for k, v in summary.items()],
        },
        highlights={"选题包": {"排期属性": "contains:固定栏目"}},
        widths={"选题包": {"选题": 38, "候选标题（3 公式）": 60, "建议角度": 34}},
    )
    js = at.write_json({"summary": summary, "package": rows, "skipped": skipped,
                        "generated_at": at.stamp(),
                        "note": "标题为模板句式草稿；正文与标题终稿须人工确认；本流程不执行发布"},
                       os.path.join(a.outdir, "topic_package.json"))
    print(f"选题包 {len(rows)} 条（热点机动位 {summary['热点机动位']}，常青 {summary['常青固定栏目']}），"
          f"跳过 {summary['跳过']} 条")
    print(" 产物:", xlsx)
    at.emit({"files": [xlsx, js], "summary": summary})


if __name__ == "__main__":
    main()
