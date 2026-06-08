# multimodal-skill — 视觉识别技能

让不支持多模态的 AI 也能"看懂"图片、截图、文档、图表。

**版本**: 3.4.0 | **更新日期**: 2026-06-09

---

## 简介

当主模型无法直接处理视觉内容时，本技能充当"眼睛"——把图片发送给专门的识图模型，结果以文字返回给主模型。

适用：照片分析、截图识别、文档查阅、图表解读、OCR 文字提取等。

## 能做什么

| 场景 | 示例 |
|------|------|
| 照片分析 | 描述场景、人物、活动、氛围、光线 |
| 截图识别 | 读取报错信息、界面文字、数据面板 |
| 文档查阅 | 定位指定页面，识别图文表格 |
| 图表解读 | 分析折线图趋势、流程图逻辑、图纸标注 |
| 文字提取 | 从图片或扫描件中提取 OCR 文字 |
| 自动优化 | 大文件压缩、API 异常重试 |

## 工作原理

```
用户: "这页讲了什么？"
        │
        ▼
┌─────────────────────────────────┐
│  主模型                          │
│  分析需求 → 拆成具体问题          │
│  "先确认页码，再问标题，最后问细节" │
└─────────────┬───────────────────┘
              │ --ask "列出核心内容" --session auto
              ▼
┌─────────────────────────────────┐
│  识图模型                        │
│  收图片 + 精准问题 → 文字回答     │
│  "本章讨论变速比转向器..."        │
└─────────────┬───────────────────┘
              │ 文字结果
              ▼
┌─────────────────────────────────┐
│  主模型                          │
│  信息够了 → 总结回答用户         │
│  不够   → --ask "追问" --session 同会话（不重传图片）
└─────────────────────────────────┘
```

首次调用时图片编码缓存，后续追问只传文字问题，大幅省时省带宽。

## 安装

### 依赖

```bash
pip install PyMuPDF    # 文档渲染（需要处理 PDF 等时必装）
pip install Pillow      # 大文件压缩（可选，不装则跳过）
```

### 获取技能

```bash
# 克隆到技能目录
git clone https://github.com/SlXiaMi/multimodal-skill.git ~/.claude/skills/multimodal-skill

# 或者放到其他 AI 工具的技能目录，目录名保持一致
```

### 配置

复制配置模板并填入自己的信息：

```bash
cp multimodal-config.example.json multimodal-config.json
```

编辑 `multimodal-config.json`：

```json
{
  "provider": "anthropic",
  "api_base_url": "https://your-api-endpoint.com",
  "api_key": "your-api-key",
  "model": "your-vision-model",
  "max_tokens": 4096,
  "compress_max_mb": 15,
  "max_retries": 3,
  "session_ttl_hours": 24
}
```

| 字段 | 说明 |
|------|------|
| `provider` | `anthropic` 或 `openai`，决定 API 请求格式 |
| `api_base_url` | API 端点地址，兼容任何实现对应格式的服务 |
| `api_key` | API 密钥。也可留空，通过 `api_key_env` 指定的环境变量读取 |
| `model` | 视觉模型名称 |
| `compress_max_mb` | 文件超过该大小自动压缩（MB），默认 15 |
| `max_retries` | API 失败最大重试次数，默认 3 |
| `session_ttl_hours` | 会话过期时间（小时），默认 24 |

验证配置：`python multimodal.py --check`

## 用法

### 基本用法

```bash
# 精准提问（推荐）
python multimodal.py <文件或网址> --ask "具体问题"

# 多轮会话（推荐，三步走）
python multimodal.py <文件或网址> --ask "首问" --session auto
python multimodal.py --ask "追问" --session auto-YYYYMMDD-NNN
python multimodal.py --session auto-YYYYMMDD-NNN --clear

# 全量描述（仅用于"描述这张图"类需求）
python multimodal.py <文件或网址>
```

### 文档页面处理

```bash
# 指定页面
python multimodal.py 文档.pdf --pdf-page 20 --ask "列出核心内容" --session auto

# 连续页面
python multimodal.py 文档.pdf --pdf-range 20-25 --ask "总结" --session auto

# 自定义清晰度
python multimodal.py 文档.pdf --pdf-page 20 --dpi 300 --ask "识别表格"
```

### 在线资源

```bash
python multimodal.py https://example.com/photo.jpg --ask "描述内容" --session auto
```

### 管理命令

```bash
python multimodal.py --check               # 验证配置
python multimodal.py --list-sessions       # 活跃会话
python multimodal.py --session <名> --export  # 导出对话
python multimodal.py --stats               # 使用统计
python multimodal.py --session <名> --clear   # 清理会话
```

## 跨平台使用

本技能基于标准 SKILL.md 规范，不限于特定 AI 工具。

| 工具 | 安装位置 | 调用方式 |
|------|---------|---------|
| Claude Code | `~/.claude/skills/` | `/multimodal-skill` 或自动发现 |
| 终端命令行 | 任意位置 | `python multimodal.py <参数>` |
| 其他 AI 工具 | 各自的 skills/rules 目录 | 将 SKILL.md 内容作为系统提示注入 |

路径中的 `~` 和 `/` 在 Windows 下自动适配为 `%USERPROFILE%` 和 `\`。

## API 兼容

| provider | 请求路径 | 认证头 |
|----------|---------|--------|
| `anthropic` | `/v1/messages` | `x-api-key` |
| `openai` | `/chat/completions` | `Authorization: Bearer` |

兼容任何实现了上述格式的端点（包括第三方代理和中转服务）。

## 文件结构

```
multimodal-skill/
├── SKILL.md                        # 技能定义
├── README.md                       # 使用手册（本文件）
├── multimodal-config.example.json  # 配置模板
├── multimodal-config.json          # 实际配置（不入库）
├── .gitignore
├── scripts/
│   └── multimodal.py               # 核心脚本
└── sessions/                       # 会话缓存（自动清理）
    └── <会话名>/
        ├── meta.json                # 对话历史
        └── image.b64                # 图片缓存
```

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-06-08 | 首版：单张图片识别 |
| 2.0.0 | 2026-06-08 | 文档页渲染、大文件压缩、重试、校验、动态超时 |
| 3.0.0 | 2026-06-08 | `--ask` 精准提问、`--session` 多轮会话 |
| 3.1.0 | 2026-06-08 | URL 下载、自动会话名、`--export`、`--stats` |
| 3.2.0 | 2026-06-08 | `--session auto` 推荐、三步模板 |
| 3.3.0 | 2026-06-08 | 话术通用化、多平台适配、补全说明 |
| 3.4.0 | 2026-06-09 | 中文为主、清理强化、引导更通用 |

## 限制

- 不支持视频（需外部工具先截图）
- 多张独立图片需逐一调用，不支持批量对比
- 会话过期前占用磁盘（自动清理）
- 识别质量取决于底层视觉模型

## 常见问题

**主模型和识图模型是同一个吗？**
不是。主模型负责对话，识图模型负责看内容。两者独立配置，互不干扰。

**会话文件占多少空间？**
约为原文件的 1.3 倍。超过 `session_ttl_hours` 后自动清理。

**大文件怎么处理？**
超过 `compress_max_mb` 自动压缩。也可 `--no-compress` 跳过。

**能同时看多张图吗？**
文档连续页用 `--pdf-range`。独立图片需逐一调用。
