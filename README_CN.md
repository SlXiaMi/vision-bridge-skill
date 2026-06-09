# vision-bridge-skill

> [English](./README_EN.md)

让不支持多模态的 AI 也能"看懂"视觉内容。

[![Version](https://img.shields.io/badge/version-4.2.0-blue)](https://github.com/SlXiaMi/vision-bridge-skill)
[![License](https://img.shields.io/badge/license-MIT-green)](./LICENSE)

---

## 简介

当主模型无法直接处理图片时，本技能充当"眼睛"——把视觉内容发送给识图模型，结果以文字返回给主模型，让它间接获得视觉理解能力。

**核心设计：** 主 AI 和识图 AI 之间用 **AI-to-AI 协议格式**（`#q @字段 >格式`）通信，高效、精准。跟用户对话用自然语言，AI 之间用协议。

---

## 快速开始

```bash
git clone https://github.com/SlXiaMi/vision-bridge-skill.git ~/.claude/skills/vision-bridge-skill
cd ~/.claude/skills/vision-bridge-skill
cp vision-bridge-config.example.json vision-bridge-config.json
# 编辑 vision-bridge-config.json，填入 API 地址、密钥和模型名
python scripts/vision-bridge.py --check
```

---

## 会话生命周期

每次识别经过 **创建 → 问答（轮次不限）→ 清理** 三个阶段：

```
❶ 创建会话 ─ vision-bridge.py <文件> --ask "问题" --session auto --output json
❷ 问答     ─ 不限轮次，信息够了就停。用协议格式（#q @字段 >格式）
❸ 清理     ─ vision-bridge.py --session <会话名> --clear（必须执行）
```

---

## 基础用法

```bash
# 单次识别
vision-bridge.py 照片.jpg --ask "#q photo @活动,地点,时间 >list" --session auto --output json

# 多轮追问（图片已缓存，秒级响应）
vision-bridge.py --ask "画面氛围如何？" --session auto-xxx --output json
vision-bridge.py --ask "有什么文字标识？" --session auto-xxx --output json

# 清理
vision-bridge.py --session auto-xxx --clear
```

### PDF 文档

```bash
# 单页
vision-bridge.py 文档.pdf --pdf-page 20 --ask "#q diagram @符号,公式 >table" --session auto

# 多页范围（并行渲染，4 线程）
vision-bridge.py 文档.pdf --pdf-range 20-25 --ask "总结这几页" --session auto

# 调整清晰度 + 增强对比度
vision-bridge.py 文档.pdf --pdf-page 1 --dpi 300 --enhance --ask "#q text @文字 >spec"
```

### 在线资源

```bash
vision-bridge.py https://example.com/chart.png --ask "#q chart @数据,趋势 >table"
```

---

## AI-to-AI 协议格式

主 AI 和识图 AI 通信使用协议格式，不用自然语言。

```
请求:  #q <图片类型> @<信息字段> ><输出格式>
响应:  #a + Markdown 表格/列表

示例:  #q diagram @符号,公式,标注 >table
       → 识图 AI 返回纯表格，无问候语、无总结
```

`@` 后面写你想知道的任何信息，**不限词汇**。`>` 指定输出格式：`table`（表格）/ `list`（列表）/ `spec`（原文照抄）。

```
#q photo @活动,地点,时间       >list
#q screenshot @文字,元素,错误   >spec
#q diagram @符号,公式,设计意图  >table
```

追问：`#q follow @上次没问到或不够深的点 >格式`

---

## 进阶功能

### `--protocol` 协议模式

自动注入高效系统指令 + 裁剪废话。识图 AI 不按格式返回时会自动重试一次。

```bash
vision-bridge.py 图表.png --ask "#q chart @数据,趋势 >table" --protocol --output json
```

### `--output json` 结构化输出

给主 AI 解析用，返回 JSON：

```json
{"answer": "...", "session": "auto-xxx", "model": "mimo-v2.5", "round": 1, "status": "ok"}
```

### 批量处理

```bash
vision-bridge.py ~/screenshots/*.png --ask "哪些有报错？"
vision-bridge.py img1.jpg img2.jpg --ask "对比差异"
vision-bridge.py ./documents/ --ask "列出所有图表标题"
```

### 多图对比

```bash
vision-bridge.py before.jpg --ask "#q photo @主体 >list" --session auto
vision-bridge.py --ask "对比差异" --session auto-xxx --add-image after.jpg
vision-bridge.py --session auto-xxx --clear
```

### `--profile` 多配置

```
profiles/
  gpt4v.json  →  --profile gpt4v
  local.json  →  --profile local
```

```bash
vision-bridge.py --profile gpt4v photo.jpg --ask "#q photo @主体,场景"
vision-bridge.py --list-profiles   # 查看可用配置
```

### `--system` 角色设定 + `--stream` 流式 + `--enhance` 图像增强

```bash
vision-bridge.py xray.png --ask "#q medical @特征 >spec" \
  --system "你是放射科医生" --protocol

vision-bridge.py chart.png --ask "#q chart @数据 >table" --stream

vision-bridge.py 模糊文档.pdf --pdf-page 1 --enhance --ask "#q text @文字 >spec"
```

---

## 管理命令

```bash
vision-bridge.py --check                      # 验证配置
vision-bridge.py --check --profile gpt4v      # 验证指定 profile
vision-bridge.py --stats                      # 使用统计
vision-bridge.py --list-sessions              # 活跃会话
vision-bridge.py --list-sessions -v           # 详细信息
vision-bridge.py --list-profiles              # 可用配置
vision-bridge.py --session <名> --status      # 会话详情
vision-bridge.py --session <名> --export      # 导出 Markdown
vision-bridge.py --session <名> --clear       # 清理会话
vision-bridge.py --version                    # 版本号
```

---

## 配置

`vision-bridge-config.json`：

```json
{
  "enabled": true,
  "provider": "anthropic",
  "api_base_url": "https://your-api-endpoint.com",
  "api_key": "your-key",
  "model": "your-vision-model",
  "max_tokens": 4096,
  "compress_max_mb": 15,
  "max_retries": 3,
  "session_ttl_hours": 24,
  "max_history_rounds": 8,
  "prompt": "默认提问内容"
}
```

| 字段 | 说明 |
|------|------|
| `provider` | `anthropic` 或 `openai` |
| `api_base_url` | API 端点地址 |
| `api_key` | API 密钥（也可用 `api_key_env` 从环境变量读取） |
| `model` | 视觉模型名称 |
| `compress_max_mb` | 超过此大小自动压缩（MB），默认 15 |
| `max_retries` | 失败重试次数，默认 3 |
| `session_ttl_hours` | 会话过期时间（小时），默认 24 |
| `max_history_rounds` | 长会话自动截断阈值，默认 8 |
| `prompt` | 未指定 `--ask` 时的默认提问 |

---

## 完整参数

| 参数 | 说明 |
|------|------|
| `file_path` | 文件路径、目录或 URL，支持多个 |
| `--ask` | 提问内容（推荐用协议格式） |
| `--output text\|json` | 输出格式，默认 text |
| `--protocol` | 协议模式：自动注入 + 裁剪废话 + 格式校验重试 |
| `--system` | 系统提示词 |
| `--stream` | 流式输出 |
| `--session auto\|<名>` | 会话管理 |
| `--add-image <文件>` | 追加图片到会话 |
| `--profile <名>` | 切换配置 |
| `--enhance` | PDF 图片对比度增强（Pillow 可选） |
| `--pdf-page N` | 指定 PDF 页码 |
| `--pdf-range M-N` | PDF 页码范围（并行渲染，4 线程） |
| `--dpi N` | 渲染 DPI，默认 200 |
| `--no-compress` | 跳过压缩 |
| `--force` | 覆盖已有会话 |
| `--verbose` `-v` | 详细输出 |
| `--format md\|txt` | 导出格式 |
| `--check` | 配置校验 |
| `--stats` | 使用统计 |
| `--list-sessions` | 会话列表 |
| `--list-profiles` | 配置列表 |
| `--clear` | 清理会话 |
| `--version` | 版本号 |

---

## 依赖

```bash
pip install PyMuPDF    # PDF 渲染（必需）
pip install Pillow      # 压缩 + 增强（可选）
```

## API 兼容

| provider | 路径 | 认证 | 适用模型 |
|----------|------|------|---------|
| `anthropic` | `/v1/messages` | `x-api-key` | Claude、MiMo |
| `openai` | `/chat/completions` | `Authorization: Bearer` | GPT-4o、DeepSeek Vision、Ollama |

---

## 文件结构

```
vision-bridge-skill/
├── SKILL.md
├── README.md          ← 语言选择页面
├── README_CN.md       ← 完整中文文档
├── README_EN.md       ← 完整英文文档
├── vision-bridge-config.json
├── vision-bridge-config.example.json
├── profiles/
│   ├── example.json
│   └── <自定义>.json
├── scripts/
│   └── vision-bridge.py       # ~1400 行
└── sessions/                  # 自动清理
```

## License

MIT
