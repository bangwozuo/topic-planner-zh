# 测试报告 —— hotspot-aggregate-scan-flow

## 一、结构校验

| 项 | 结果 |
|---|---|
| 四件套齐全（SKILL.md / prompt.txt / schema.json / examples/input.json） | ✅ PASS |
| SKILL.md 九段齐全 + frontmatter + ID 行（de_media_01_wf01） | ✅ PASS |
| prompt.txt ≥ 1200 字（T3 标准），实测约 2560 字 | ✅ PASS |
| 引用原子技能真实存在（hot-topic-radar / competitor-track 均在同仓 skills/ 且可跑） | ✅ PASS |
| 无占位符残留 | ✅ PASS |

## 二、端到端实跑

**命令**：

```bash
python scripts/run_flow.py --demo
python scripts/run_flow.py --input examples/input.json --outdir out
```

**运行环境**：Windows 11 · Python 3.13（WorkBuddy 内置环境）

| 项 | 结果 |
|---|---|
| 退出码 | 0 |
| 步骤 1 | 子进程调用 radar_scan.py ✅ → out/radar_scan.json（2.6 KB）+ 热点候选池.xlsx + 热点平台分布.png |
| 步骤 2 | 子进程调用 competitor_track.py ✅ → out/competitor_track.json（3.5 KB）+ 竞品追踪报告.xlsx + 竞品互动对比.png |
| 步骤 3 | 合并 → out/每日候选池.xlsx（7.8 KB，A 级行标红）+ out/daily_pool.json（2.4 KB） |
| 耗时 | < 8 s（含两个子进程） |

### 执行摘要（真实输出）

```text
步骤 1  hot-topic-radar      ✅  → out/radar_scan.json
步骤 2  competitor-track     ✅  → out/competitor_track.json
步骤 3  合并候选池            ✅  → out/每日候选池.xlsx
汇总    候选 5 条
```

### 降级路径实测

| 场景 | 输入 | 结果 |
|---|---|---|
| 双空输入 | hotlist/competitors 均空 | 「今日无输入」占位清单，退出码 0，不编造 ✅ |
| 热榜为空 | 仅 competitors | 「降级为纯竞品日」正常完成 ✅ |
| 竞品为空 | 仅 hotlist | 「降级为纯热点日」正常完成 ✅ |

## 三、编排规则核验

| 规则 | 实测 |
|---|---|
| 上游失败中止 | run_step 校验退出码与 JSON 产物存在性，缺失即 sys.exit(1) ✅ |
| 红线不进池 | 地震条目（归一 100.0）仅出现在汇总计数与淘汰说明 ✅ |
| 竞品占比 ≤40% | 5 条候选中竞品衍生 2 条，正好触上限不再进池 ✅ |
| 数值不二次计算 | 候选池得分直接取上游 JSON（101.8/23.0/15.4/7.9x/6.0x） ✅ |
| 人工确认 | 候选池交付后由人工决策，无自动排期动作 ✅ |

## 四、边界与已知限制

| 限制 | 说明 |
|---|---|
| 数据来源 | 热榜靠人工粘贴，无爬虫；缺平台数据走降级而非补造 |
| 时效 | 候选池为 07:30 时点快照，午后爆发的新热点次日才会进池 |
| 上游依赖 | 两个技能脚本更新后需回归本流程（合并字段名耦合上游 schema） |

## 五、结论

**通过。** 端到端实跑三步全绿，产出候选池 Excel + JSON 及上游四类中间产物；
红线拦截、竞品占比上限、双空占位、降级路径四类规则实测生效；
候选池 Top1 为「时效×垂直=爆款区」的真实机器判定。

---

*测试报告基于真实实跑输出生成 · 2026-09-30*
