---
name: multimodal-skill
description: >-
  视觉识别、图像理解、截图分析、文档扫描、图表解读、OCR文字提取、多轮追问。
  当需要"看"任何视觉内容（图片、照片、截图、PDF、图表、扫描件、技术图纸等）时激活。
  主模型分析需求，精准提问，识图模型回答。支持多轮对话逐步深入。
license: MIT
metadata:
  author: Claude Code
  version: 3.3.0
  created: 2026-06-08
  last_reviewed: 2026-06-08
  review_interval_days: 90
  dependencies:
    - library: PyMuPDF
      name: 文档页面渲染（处理 PDF 等需要）
    - library: Pillow
      name: 大图自动压缩（可选，未安装时跳过）
---

# /multimodal-skill — 视觉识别

脚本位置：`skills/multimodal-skill/scripts/multimodal.py`（相对于 skills 根目录）

---

## 三步工作模板

每次需要"看"视觉内容时：

```
第 ❶ 步 — 确认目标 + 首问
  multimodal.py <文件路径> --ask "精准问题" --session auto
  （自动创建会话，内容只编码一次）

第 ❷ 步 — 追问（信息不够时）
  multimodal.py --ask "下一个问题" --session <会话名>
  （不带文件路径，复用缓存，不重传）

第 ❸ 步 — 收尾
  multimodal.py --session <会话名> --clear
```

**原则：**
- 加 `--ask`，带着目的去问，不盲目全量描述
- 预计需要多步分析 → 加上 `--session auto`
- 追问不带文件路径，缓存已复用
- 用户意图模糊时先确认，别猜

## 命令速查

```
multimodal.py <文件> --ask "..." --session auto    常规用法
multimodal.py --ask "..." --session <名>            追问（不带路径）
multimodal.py <文件> --pdf-page N --ask "..."       文档指定页
multimodal.py <文件> --pdf-range M-N --ask "..."    文档连续页
multimodal.py <URL> --ask "..."                     在线图片
multimodal.py --check                               校验配置
multimodal.py --stats                               使用统计
multimodal.py --list-sessions                       活跃会话
multimodal.py --session <名> --export               导出对话
multimodal.py --session <名> --clear                清理会话
```

## 使用示例

```
# 照片场景
multimodal.py ~/photo.jpg --ask "描述场景和人物" --session auto
multimodal.py --ask "画面氛围如何？光线怎样？" --session auto-20260608-001
multimodal.py --session auto-20260608-001 --clear

# 截图场景
multimodal.py ~/screenshot.png --ask "识别所有文字和错误信息" --session auto

# 文档场景
multimodal.py ~/report.pdf --pdf-page 20 --ask "列出核心内容" --session auto
multimodal.py --ask "详细解释第三点" --session auto-20260608-001
multimodal.py --session auto-20260608-001 --clear

# 图表场景
multimodal.py ~/chart.jpg --ask "X轴Y轴分别是什么？趋势如何？" --session auto
```

## 能力总览

| 能力 | 说明 |
|------|------|
| 图像理解 | 照片、截图、插画等常见图片格式 |
| 文档扫描 | PDF、扫描件等，自动渲染后识别 |
| 图表解读 | 折线图、柱状图、流程图、技术图纸 |
| OCR 文字提取 | 识别图片/扫描件中的文字内容 |
| 大文件压缩 | 自动缩图，避免超时 |
| 故障自愈 | API 异常自动等待重试 |
| 多轮对话 | 会话缓存，追问不重传 |

## 配置

配置文件：`multimodal-config.json`（与 SKILL.md 同目录）

```json
{
  "provider": "anthropic",
  "api_base_url": "https://your-api-endpoint.com",
  "api_key": "your-key",
  "model": "your-model",
  "max_tokens": 4096,
  "compress_max_mb": 15,
  "max_retries": 3,
  "session_ttl_hours": 24
}
```

| 字段 | 说明 |
|------|------|
| `provider` | API 格式：`anthropic` 或 `openai` |
| `api_key` | 直接填或留空用环境变量 `api_key_env` |
| `model` | 可用的视觉模型名称 |
| `compress_max_mb` | 超过此大小自动压缩（单位 MB） |
| `max_retries` | API 失败最大重试次数 |
| `session_ttl_hours` | 会话自动过期时间（小时） |

## 故障排查

| 症状 | 方向 |
|------|------|
| API Key 无效 | `--check` 验证连接和权限 |
| 文档页渲染失败 | 确认 `PyMuPDF` 已安装 |
| 会话不存在 | 先创建：带文件路径 + `--session auto` |
| 会话名冲突 | `--force` 覆盖或换名 |
| 网络超时 | 检查代理/VPN；大文件会自动压缩 |
| URL 下载失败 | 确认链接可直接访问 |
