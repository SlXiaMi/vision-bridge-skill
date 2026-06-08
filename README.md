# multimodal-skill — 视觉识别技能

让 AI 能"看懂"图片、截图、文档、图表。

**版本**: 3.3.0 | **更新日期**: 2026-06-08

---

## 简介

当主模型不支持视觉能力时，本技能充当"眼睛"——将视觉内容发送给专门的识图模型，把结果以文字形式返回给主模型继续处理。

适用场景：照片分析、截图识别、文档查阅、图表解读、OCR 文字提取等。

## 它能做什么

| 场景 | 示例 |
|------|------|
| 图像理解 | 描述照片内容、场景、人物、氛围 |
| 截图识别 | 读取报错信息、界面文字、数据面板 |
| 文档查阅 | 定位 PDF 指定页，识别图文和表格 |
| 图表解读 | 分析折线图趋势、流程图逻辑、技术图纸标注 |
| OCR 提取 | 从图片/扫描件中提取文字内容 |
| 自动优化 | 大文件自动压缩、API 异常自动重试 |

## 工作原理

```
用户: "这页文档讲了什么？"
        │
        ▼
┌─────────────────────────────────┐
│  主模型                          │
│  分析需求 → 拆解为具体问题        │
│  "先确认页码，再问标题，最后问细节" │
└─────────────┬───────────────────┘
              │ --ask "列出核心内容" --session auto
              ▼
┌─────────────────────────────────┐
│  识图模型                        │
│  接收图片 + 精准问题 → 返回文字   │
│  "本章讨论变速比转向器..."        │
└─────────────┬───────────────────┘
              │ 文字结果
              ▼
┌─────────────────────────────────┐
│  主模型                          │
│  信息够了 → 总结回答用户         │
│  不够 → --ask "追问细节" --session <同会话>
└─────────────────────────────────┘
```

**多轮会话机制**：首次调用时图片被编码缓存，后续追问只需传文字问题，大幅节省时间和带宽。

## 安装

技能目录：`~/.claude/skills/multimodal-skill/`

### 依赖

```bash
pip install PyMuPDF    # 文档渲染（处理 PDF 等需要）
pip install Pillow      # 大图自动压缩（可选）
```

### 配置

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
| `provider` | API 格式：`anthropic` 或 `openai` |
| `api_base_url` | API 端点地址 |
| `api_key` | API 密钥（也可通过 `api_key_env` 指定环境变量读取） |
| `model` | 视觉模型名称 |
| `compress_max_mb` | 超过此阈值自动压缩（默认 15 MB） |
| `max_retries` | 失败重试上限 |
| `session_ttl_hours` | 会话过期时间 |

验证配置：`python multimodal.py --check`

## 命令参考

### 基本用法

```bash
# 精准提问（推荐）
python multimodal.py <文件或URL> --ask "具体问题"

# 多轮会话（推荐）
python multimodal.py <文件或URL> --ask "首问" --session auto
python multimodal.py --ask "追问" --session auto-YYYYMMDD-NNN
python multimodal.py --session auto-YYYYMMDD-NNN --clear

# 默认描述（仅用于"描述这张图"类需求）
python multimodal.py <文件或URL>
```

### 文档处理

```bash
# 指定页面
python multimodal.py document.pdf --pdf-page 20 --ask "列出核心内容" --session auto

# 连续页面
python multimodal.py document.pdf --pdf-range 20-25 --ask "总结这几页" --session auto

# 自定义渲染质量
python multimodal.py document.pdf --pdf-page 20 --dpi 300 --ask "识别表格数据"
```

### 工具

```bash
python multimodal.py --check               # 验证 API 配置
python multimodal.py --list-sessions       # 活跃会话列表
python multimodal.py --session <名> --export  # 导出会话文本
python multimodal.py --stats               # 使用统计
python multimodal.py --session <名> --clear   # 清理会话
```

## API 兼容性

| provider | 请求格式 | 认证头 |
|----------|---------|--------|
| `anthropic` | `/v1/messages` | `x-api-key` |
| `openai` | `/chat/completions` | `Authorization: Bearer` |

兼容任何实现了上述格式的 API 端点（包括第三方代理和中转服务）。

## 文件结构

```
multimodal-skill/
├── SKILL.md                   # 技能定义
├── README.md                  # 使用手册（本文件）
├── multimodal-config.json     # API 配置
├── scripts/
│   └── multimodal.py          # 核心脚本
└── sessions/                  # 会话缓存（自动清理）
    └── <name>/
        ├── meta.json           # 对话历史
        └── image.b64           # 图片缓存
```

## 多平台使用

| 平台 | 脚本调用方式 |
|------|-------------|
| Claude Code | 自动发现 `/multimodal-skill` |
| 终端直接调用 | `python multimodal.py <参数>` |
| 其他 AI 工具 | 将 SKILL.md 内容作为系统提示注入 |

路径示例使用 `~` 和 `/`，Windows 下自动适配为 `%USERPROFILE%` 和 `\`。

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-06-08 | 首版：单张图片识别 |
| 2.0.0 | 2026-06-08 | 文档页渲染、大文件压缩、重试机制、配置校验、动态超时 |
| 3.0.0 | 2026-06-08 | 精准提问 `--ask`、多轮会话 `--session`、会话管理 |
| 3.1.0 | 2026-06-08 | URL 下载、自动会话名、`--export`、`--stats` |
| 3.2.0 | 2026-06-08 | `--session auto` 定为推荐默认、三步工作模板 |
| 3.3.0 | 2026-06-08 | 话术通用化、补全能力总览和配置说明、多平台适配 |

## 限制与已知问题

- 不支持视频帧提取（需外部工具先截图）
- 多张独立图片需逐一调用，不支持批量对比
- 会话文件在过期前会占用磁盘（超时自动清理）
- 识别质量取决于底层视觉模型的能力

## 常见问题

**Q: 主模型和识图模型是同一个吗？**
A: 不是。主模型负责对话和逻辑，识图模型专门处理视觉内容，两者独立配置，互不干扰。

**Q: 会话文件占用多少空间？**
A: 每张图片以编码形式存储，大致为原始文件的 1.3 倍。超过 `session_ttl_hours` 后自动清理。

**Q: 如何处理超大文件？**
A: 超过 `compress_max_mb`（默认 15MB）会自动压缩至合理尺寸。可用 `--no-compress` 跳过。

**Q: 能同时处理多张图吗？**
A: 文档连续页用 `--pdf-range`。多张独立图片需逐一调用，每次一个会话。
