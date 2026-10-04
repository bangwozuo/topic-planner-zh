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
| [`out/_step_dedup_input.json`](out/_step_dedup_input.json) | 结构化结果（实跑生成） · 1 KB |
| [`out/dedup_check.json`](out/dedup_check.json) | 结构化结果（实跑生成） · 2 KB |
| [`out/dedup_match_result.json`](out/dedup_match_result.json) | 结构化结果（实跑生成） · 3 KB |
| [`out/去重后选题榜.xlsx`](out/去重后选题榜.xlsx) | Excel 工作簿（实跑生成） · 9 KB |
| [`out/选题去重清单.xlsx`](out/选题去重清单.xlsx) | Excel 工作簿（实跑生成） · 7 KB |


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

工作流缺少初始输入数据，无法启动「选题库去重匹配」端到端执行。

## 分步结果

1. 步骤 1：选题去重校验 — **未执行**（原因：缺少 reference、target 等初始输入）
2. 步骤 2：选题知识库 — **未执行**（原因：上一步未产出有效结果，不具备继续条件）

## 最终交付物

无。请提供以下信息后重新运行：

- `reference`：基准材料 — 作为对照的原始/标准材料
- `target`：待校验材料 — 需要校验的对象


---

*运行效果由实跑验证生成*
