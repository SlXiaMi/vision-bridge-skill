# vision-bridge-skill

让不支持多模态的 AI 也能"看懂"视觉内容。

[![Version](https://img.shields.io/badge/version-3.4.0-blue)](https://github.com/SlXiaMi/vision-bridge-skill)
[![License](https://img.shields.io/badge/license-MIT-green)](./LICENSE)

---

## 简介

当主模型（如 DeepSeek 等纯文本模型）无法直接处理图片时，本技能充当"眼睛"——把视觉内容发送给专门的识图模型，结果以文字返回给主模型，让它间接获得视觉理解能力。

**适用场景：** 照片分析、截图识别、文档查阅、图表解读、OCR 文字提取。

## 快速开始

三步即可使用：

```bash
# ❶ 安装
git clone https://github.com/SlXiaMi/vision-bridge-skill.git ~/.claude/skills/vision-bridge-skill

# ❷ 配置
cd ~/.claude/skills/vision-bridge-skill
cp multimodal-config.example.json multimodal-config.json
# 编辑 multimodal-config.json，填入你的 API 地址、密钥和模型名

# ❸ 验证
python scripts/multimodal.py --check
```

## 效果演示

```
用户: 这张照片讲了什么故事？

主模型: [调用 multimodal.py photo.jpg --ask "描述场景和活动" --session auto]
识图模型: 绿色草坪上，家长和孩子共同托举彩虹伞，周围有卡通充气道具...
主模型: [追问: --ask "参与者的年龄和着装？" --session auto-20260609-001]
识图模型: 儿童约3-7岁穿统一校服，成人着便装，红色马甲志愿者...
主模型: [清理会话]
        → 总结回答用户：这是一场幼儿园亲子运动会...
```

## 使用方式

### 基本用法

```bash
# 精准提问（推荐 —— 带着目的问，不盲目全量描述）
python scripts/multimodal.py 照片.jpg --ask "描述人物和场景" --session auto

# 多轮追问（信息不够就继续，不限轮次）
python scripts/multimodal.py --ask "画面氛围如何？" --session auto-20260609-001
python scripts/multimodal.py --ask "有什么文字标识？" --session auto-20260609-001

# 完成必须清理
python scripts/multimodal.py --session auto-20260609-001 --clear
```

### 文档页面

```bash
python scripts/multimodal.py 文档.pdf --pdf-page 20 --ask "列出核心内容" --session auto
python scripts/multimodal.py 文档.pdf --pdf-range 20-25 --ask "总结这几页" --session auto
```

### 在线资源

```bash
python scripts/multimodal.py https://example.com/chart.png --ask "分析趋势" --session auto
```

### 管理命令

```bash
python scripts/multimodal.py --check               # 验证配置
python scripts/multimodal.py --list-sessions       # 活跃会话列表
python scripts/multimodal.py --stats               # 使用统计
python scripts/multimodal.py --session <名> --export  # 导出对话
python scripts/multimodal.py --session <名> --clear   # 清理会话
```

## 工作原理

```
用户提问
    │
    ▼
┌──────────────┐     ┌──────────────┐
│  主模型       │────▶│  识图模型     │
│  分析需求     │ 图片 │  接收视觉内容 │
│  拆解问题     │+问题│  返回文字描述 │
│  决策追问     │◀────│              │
└──────────────┘ 文字 └──────────────┘
    │
    ▼
  整理回答 → 返回用户

会话机制：图片只编码一次，后续追问只传文字，秒级响应。
```

## 配置

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

| 字段 | 必填 | 说明 |
|------|------|------|
| `provider` | 是 | `anthropic` 或 `openai`，决定 API 请求格式 |
| `api_base_url` | 是 | API 端点地址，兼容任何实现对应格式的服务 |
| `api_key` | 是 | API 密钥。也可留空，通过 `api_key_env` 从环境变量读取 |
| `model` | 是 | 视觉模型名称 |
| `max_tokens` | 否 | 单次返回上限，默认 4096 |
| `compress_max_mb` | 否 | 超过此大小自动压缩（MB），默认 15 |
| `max_retries` | 否 | 失败重试次数，默认 3 |
| `session_ttl_hours` | 否 | 会话过期时间（小时），默认 24 |

## 命令参数

| 参数 | 说明 |
|------|------|
| `--ask "问题"` | 精准提问，替代全量描述 |
| `--session auto` | 自动创建会话（推荐） |
| `--session <名>` | 指定会话名 |
| `--pdf-page N` | 文档指定页码 |
| `--pdf-range M-N` | 文档连续页码 |
| `--dpi N` | 文档渲染清晰度（默认 200） |
| `--no-compress` | 跳过自动压缩 |
| `--force` | 覆盖已有会话 |
| `--export` | 导出会话对话文本 |
| `--profile <名>` | 切换配置方案 |
| `--check` | 验证 API 配置 |
| `--stats` | 使用统计 |
| `--list-sessions` | 活跃会话列表 |

## 依赖

```bash
pip install PyMuPDF    # 文档渲染（处理 PDF 等需要，必需）
pip install Pillow      # 大文件压缩（可选，不装则跳过）
```

## API 兼容

| provider | 请求路径 | 认证头 | 适用模型举例 |
|----------|---------|--------|-------------|
| `anthropic` | `/v1/messages` | `x-api-key` | Claude、MiMo 及兼容 API |
| `openai` | `/chat/completions` | `Authorization: Bearer` | GPT-4o、DeepSeek Vision 及兼容 API |

**只要 API 端点实现了上述格式，无论官方还是第三方中转，均可使用。**

## 跨平台

本技能基于标准 SKILL.md 规范，可在多个 AI 工具中使用。

| 工具 | 安装位置 | 调用方式 |
|------|---------|---------|
| Claude Code | `~/.claude/skills/` | `/vision-bridge-skill` 或自动发现 |
| 终端命令行 | 任意位置 | `python scripts/multimodal.py <参数>` |
| 其他兼容工具 | 各自的 skills/rules 目录 | 将 SKILL.md 内容作为系统提示注入 |

## 文件结构

```
vision-bridge-skill/
├── SKILL.md                        # 技能定义
├── README.md                       # 本文件
├── multimodal-config.example.json  # 配置模板
├── multimodal-config.json          # 实际配置（不入库）
├── .gitignore
├── scripts/
│   └── multimodal.py               # 核心脚本（~900 行）
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
| 3.2.0 | 2026-06-08 | `--session auto` 定为推荐、三步工作模板 |
| 3.3.0 | 2026-06-08 | 话术通用化、多平台适配 |
| 3.4.0 | 2026-06-09 | 中文为主、清理强化、面向 GitHub 重新组织 |

## 限制

- 不支持视频（需外部工具先截图）
- 多张独立图片需逐一调用，不支持批量对比
- 会话过期前占用磁盘（超时自动清理，默认 24h）
- 识别质量取决于底层视觉模型的能力

## License

MIT
