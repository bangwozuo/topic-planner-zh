# 截图与录屏

> 以下素材均来自**真实执行**：`--run` 实拍终端 / 实跑产物文件，无摆拍。

## 演示视频

![演示视频](assets/demo.mp4)

*四幕检测叙事（Hyperframes 动态渲染 17s）：业务钩子 → 真实执行 → 检查项逐条亮灯 → 交付物*

## 执行截图

![真实执行](assets/run-terminal.png)

## 实跑产物

| 文件 | 说明 |
|---|---|
| [`out/_step_comp_input.json`](out/_step_comp_input.json) | 结构化结果（实跑生成） · 1 KB |
| [`out/_step_radar_input.json`](out/_step_radar_input.json) | 结构化结果（实跑生成） · 1 KB |
| [`out/competitor_track.json`](out/competitor_track.json) | 结构化结果（实跑生成） · 3 KB |
| [`out/daily_pool.json`](out/daily_pool.json) | 结构化结果（实跑生成） · 2 KB |
| [`out/radar_scan.json`](out/radar_scan.json) | 结构化结果（实跑生成） · 3 KB |
| [`out/每日候选池.xlsx`](out/每日候选池.xlsx) | Excel 工作簿（实跑生成） · 8 KB |
| [`out/热点候选池.xlsx`](out/热点候选池.xlsx) | Excel 工作簿（实跑生成） · 8 KB |
| [`out/热点平台分布.png`](out/热点平台分布.png) | 图表产物（实跑生成） · 23 KB |
| [`out/竞品互动对比.png`](out/竞品互动对比.png) | 图表产物（实跑生成） · 23 KB |
| [`out/竞品追踪报告.xlsx`](out/竞品追踪报告.xlsx) | Excel 工作簿（实跑生成） · 8 KB |


---

## 附录：实跑输出明细

> 本资产为纯提示词客户端资产，无界面可截图。以下为**实跑运行效果**。

## 运行效果

### 输入

```json
{
  "input": "请提供工作流的初始输入数据"
}

```

### 输出

> AI 生成内容

## 执行摘要

工作流缺少初始输入数据，无法启动「热点聚合扫描」端到端执行。

## 分步结果

1. 步骤 1：全平台热点雷达 — **未执行**（原因：缺少 source、scope 等初始输入）
2. 步骤 2：竞品动态追踪 — **未执行**（原因：上一步未产出有效结果，不具备继续条件）

## 最终交付物

无。请提供以下信息后重新运行：

- `source`：数据来源 — 平台名 / subreddit / 关键词 / 账号或链接清单
- `scope`：采集范围 — 时间窗口、条数上限、筛选条件（可选）


---

*运行效果由实跑验证生成*
