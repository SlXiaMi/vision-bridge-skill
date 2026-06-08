---
name: vision-bridge-skill
description: >-
  视觉识别：看照片、截图、文档、图表、扫描件。主模型分析需求、精准提问，识图模型回答。支持多轮追问逐步深入。
license: MIT
metadata:
  author: Claude Code
  version: 3.4.0
  created: 2026-06-08
  last_reviewed: 2026-06-09
  review_interval_days: 90
  dependencies:
    - library: PyMuPDF
      name: 文档页面渲染
    - library: Pillow
      name: 大文件自动压缩（可选）
---

# /vision-bridge-skill — 视觉识别

脚本路径：`skills/vision-bridge-skill/scripts/multimodal.py`

---

## 三步工作模板

每次需要"看"任何视觉内容，按以下三步操作。**完成必须清理，不可省略第三步。**

```
❶ 首问（创建会话，内容编码一次）
  multimodal.py <文件路径或网址> --ask "第一个精准问题" --session auto
  → 会话名自动生成，如 auto-20260609-001

❷ 追问（信息不够就继续，不限轮次）
  multimodal.py --ask "下一个问题" --session auto-20260609-001
  → 不带文件路径！缓存已复用，秒级响应

❸ 收尾（必须执行）
  multimodal.py --session auto-20260609-001 --clear
  → 不清理也无大碍，24 小时后自动过期
```

**四条原则：**
- 始终带 `--ask`，带着目的问，不盲目全量描述
- 预计需要多步分析就加 `--session auto`
- 追问时不带文件路径
- 完成必须 `--clear`

## 命令速查

```
multimodal.py <文件> --ask "..." --session auto     日常用法
multimodal.py --ask "..." --session <会话名>         追问
multimodal.py <文件> --pdf-page N --ask "..."        指定页面
multimodal.py <文件> --pdf-range M-N --ask "..."     连续页面
multimodal.py <网址> --ask "..."                     在线资源
multimodal.py --check                                校验配置
multimodal.py --stats                                使用统计
multimodal.py --list-sessions                        活跃会话
multimodal.py --session <名> --export                导出对话
multimodal.py --session <名> --clear                 清理会话
```

## 示例

```
# 看照片
multimodal.py ~/photo.jpg --ask "描述场景、人物和活动" --session auto
multimodal.py --ask "画面氛围和光线如何？" --session auto-20260609-001
multimodal.py --session auto-20260609-001 --clear

# 看截图
multimodal.py ~/screenshot.png --ask "识别所有文字和错误信息" --session auto
multimodal.py --session auto-20260609-001 --clear

# 看文档
multimodal.py ~/doc.pdf --pdf-page 20 --ask "列出核心内容" --session auto
multimodal.py --ask "详细解释第三点" --session auto-20260609-001
multimodal.py --session auto-20260609-001 --clear

# 看图表
multimodal.py ~/chart.png --ask "横纵轴含义？趋势如何？" --session auto
multimodal.py --session auto-20260609-001 --clear

# 看在线图片
multimodal.py https://example.com/diagram.png --ask "描述流程" --session auto
```

## 能力范围

| 场景 | 说明 |
|------|------|
| 照片分析 | 场景、人物、活动、氛围 |
| 截图识别 | 报错信息、界面文字、数据面板 |
| 文档查阅 | 指定页码、图表、表格 |
| 图表解读 | 趋势图、流程图、技术图纸 |
| 文字提取 | 图片或扫描件中的 OCR 文字 |
| 自动优化 | 大文件自动压缩、API 异常重试 |
| 多轮对话 | 会话缓存，追问不重传 |

## 配置

配置文件 `multimodal-config.json`，与 SKILL.md 同目录：

```json
{
  "provider": "anthropic",
  "api_base_url": "https://your-api-endpoint.com",
  "api_key": "your-key",
  "model": "your-vision-model",
  "max_tokens": 4096,
  "compress_max_mb": 15,
  "max_retries": 3,
  "session_ttl_hours": 24
}
```

| 字段 | 说明 |
|------|------|
| `provider` | `anthropic` 或 `openai`，决定请求格式 |
| `api_key` | API 密钥，也可通过 `api_key_env` 从环境变量读取 |
| `model` | 视觉模型名称 |
| `compress_max_mb` | 超过此大小自动压缩（MB），默认 15 |
| `max_retries` | 失败重试上限，默认 3 |
| `session_ttl_hours` | 会话过期时间（小时），默认 24 |

## 故障排查

| 现象 | 方向 |
|------|------|
| 调用报错 | `--check` 验证 Key 和网络 |
| 文档页渲染失败 | `pip install PyMuPDF` |
| 会话不存在 | 先创建：带文件路径 + `--session auto` |
| 会话名冲突 | `--force` 覆盖，或换名 |
| 大文件超时 | 自动压缩中；可调高 `compress_max_mb` |
| 网络不通 | 检查代理或 VPN |
