# 选题策划师

> **每天早会前 5 分钟交付"今日选题包"的选题合伙人**

[![Stage](https://img.shields.io/badge/stage-P0-orange)](https://github.com/bangwozuo)
[![Asset](https://img.shields.io/badge/asset-prompt--only-blueviolet)](#资产形态)
[![NoKey](https://img.shields.io/badge/API%20Key-not%20required-success)](#资产形态)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)

---

## 它是谁

面向 **自媒体创作者** 的数字员工资产包。

| 项目 | 内容 |
|------|------|
| 目标用户 | 全体内容创作者（5000 万+，据 R2 调研），尤其日更压力的短视频/图文作者 |
| 交付物 | 选题包采纳率 ≥40%；每日选题耗时从 1h 压缩至 ≤10 分钟；选题库月净增 ≥30 条 |
| 技能数 | 6 |
| 工作流数 | 4 |
| 旧名存档 | `爆款选题策划师` |

---

## 资产形态

**纯提示词资产** —— 这是理解本仓库的关键：

| 特性 | 说明 |
|------|------|
| ✅ 无需 API Key | 一个 Key 都不需要 |
| ✅ 无需部署 | 没有服务端，没有脚本 |
| ✅ 无需依赖 | 克隆后用文本编辑器就能看 |
| ✅ 平台无关 | 粘贴到任何 AI 工具即可使用 |
| ✅ 用户自备算力 | 模型来自你自己的订阅 |

---

## 快速开始

```text
1. 打开 skills/hot-topic-radar/prompt.txt
2. 全文复制
3. 粘贴到你常用的 AI 工具（Coze / WorkBuddy / Dify / Claude / ChatGPT）
4. 按 SKILL.md 的输入规格提供数据
```

就这四步。完整指引见 [使用手册](docs/04-usage.md)。

---

## 仓库结构

```text
topic-planner-zh/
├── README.md / employee.md / package.yaml     # 入口与 12 字段定义卡
├── docs/01~07                                 # 员工级文档（架构/流程/场景/手册/示例/录像/测试）
├── skills/                                    # 6 个原子技能
│   └── <skill>/
│       ├── README.md  SKILL.md  prompt.txt  schema.json  examples/
│       └── docs/                              # 该技能自己的 10 项文档 + 配图
├── workflows/                                 # 4 条工作流（复合技能）
│   └── <workflow>/
│       ├── README.md  SKILL.md  prompt.txt  schema.json  examples/
│       └── docs/                              # 该工作流自己的 10 项文档 + 配图
├── knowledge/                                 # RAG wiki 知识库
│   ├── README.md  RAG-接入指南.md  template.md
│   └── wiki/(index.md, _template.md, entries/)
├── connectors/                                # 连接器说明 + 合规红线
├── quality/                                   # 效果基线与追踪日志
└── tests/                                     # 资产校验测试（离线，无需密钥）
```

### 每个技能 / 工作流自带的 docs

| 文档 | 内容 |
|------|------|
| `README.md` | 资产速览与快速开始 |
| `docs/01-usage-manual.md` | 安装使用手册 |
| `docs/02-architecture.md` | 业务架构图 |
| `docs/03-flow.md` | 流程图（Mermaid + 配图） |
| `docs/04-examples.md` | 使用示例 |
| `docs/05-media.md` | 截图和录屏（清单 + 分镜脚本） |
| `docs/06-scenarios.md` | 使用场景（适用 / 不适用） |
| `docs/07-audience.md` | 用户群体 |
| `docs/08-value.md` | 解决问题与价值 |
| `docs/09-test-report.md` | 测试报告 |
| `docs/assets/overview.svg` | 自动生成的流程示意图 |

---

## 交付物导航

| 文档 | 内容 |
|------|------|
| [业务架构](docs/01-architecture.md) | 四层架构 + 数据流 + 能力边界 |
| [工作流流程](docs/02-workflow.md) | 4 条工作流的 DAG 可视化 |
| [使用场景](docs/03-scenarios.md) | 3 个真实场景（含前后对比） |
| [使用手册](docs/04-usage.md) | 各平台导入指引 + 常见问题 |
| [示例库](docs/05-examples.md) | 6 组输入输出示例 |
| [录像脚本](docs/06-recording-script.md) | 7 镜头分镜 + 旁白稿 |
| [校验报告](docs/07-test-report.md) | 资产质量校验结果 |

---

## 技能清单（6 个）

| # | 技能 | 能力族 | 复杂度 | 提示词 | 文档 |
|---|------|--------|--------|--------|------|
| 1 | 全平台热点雷达 | 数据采集 | `M` | [prompt.txt](skills/hot-topic-radar/prompt.txt) | [docs](skills/hot-topic-radar/docs/) |
| 2 | 竞品动态追踪 | 摘要提炼 | `M` | [prompt.txt](skills/competitor-track/prompt.txt) | [docs](skills/competitor-track/docs/) |
| 3 | 选题去重校验 | 选题创意 | `S` | [prompt.txt](skills/topic-dedup-check/prompt.txt) | [docs](skills/topic-dedup-check/docs/) |
| 4 | 选题知识库 | 标签话题 | `S` | [prompt.txt](skills/topic-knowledge-base/prompt.txt) | [docs](skills/topic-knowledge-base/docs/) |
| 5 | 爆款标题锻造 | 上架优化 | `S` | [prompt.txt](skills/viral-title-craft/prompt.txt) | [docs](skills/viral-title-craft/docs/) |
| 6 | 爆款结构拆解 | 文案生成 | `S` | [prompt.txt](skills/viral-structure-decode/prompt.txt) | [docs](skills/viral-structure-decode/docs/) |

## 工作流清单（4 条）

| # | 工作流 | 阶段 | 复杂度 | 触发 | 定义 | 文档 |
|---|--------|------|--------|------|------|------|
| 1 | 热点聚合扫描 | `P0` | `M` | 定时（每日 07:30） | [SKILL.md](workflows/hotspot-aggregate-scan-flow/SKILL.md) | [docs](workflows/hotspot-aggregate-scan-flow/docs/) |
| 2 | 选题库去重匹配 | `P0` | `S` | 事件（WF1 完成后自动） | [SKILL.md](workflows/topic-lib-dedup-match-flow/SKILL.md) | [docs](workflows/topic-lib-dedup-match-flow/docs/) |
| 3 | 选题包生成 | `P0` | `S` | 事件（WF2 后自动，每日 08:00 前交付） | [SKILL.md](workflows/topic-package-generate-flow/SKILL.md) | [docs](workflows/topic-package-generate-flow/docs/) |
| 4 | 每周选题复盘 | `P1` | `M` | 定时（每周一 09:00） | [SKILL.md](workflows/weekly-topic-review-flow/SKILL.md) | [docs](workflows/weekly-topic-review-flow/docs/) |

---

## 知识库与连接器

| 目录 | 说明 |
|------|------|
| [`knowledge/`](knowledge/README.md) | RAG wiki 知识库：填入业务信息可显著提升输出质量 |
| [`connectors/`](connectors/README.md) | 连接器说明：数据从哪来、怎么合规地来 |

---

## 资产校验

```bash
pip install -r requirements.txt
pytest tests/ -v
```

校验技能完整性、提示词结构、契约一致性、工作流 DAG、技能级与工作流级 docs 完整性、知识库 wiki 与连接器结构。
**不需要任何 API Key。**

---

## 合规声明

- ✅ 所有输出为 **AI 辅助生成**，交付前须人工审核
- ✅ 提示词内置**违禁词禁止清单**，符合《广告法》要求
- ✅ 遵循《人工智能生成合成内容标识办法》
- ✅ 连接器只走**官方 API** 或**用户导出数据**
- ✅ 所有对外发布动作**保留人工确认环节**

---

## 许可

[Apache-2.0](LICENSE) — 可自由使用、修改、商用

---

*由 bangwozuo 业务库自动生成 · 2026-09-29*
