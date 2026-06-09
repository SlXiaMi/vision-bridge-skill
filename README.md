# vision-bridge-skill

> [中文](#中文) | [English](#english)

让不支持多模态的 AI 也能"看懂"视觉内容。<br>
Give AI models without vision the ability to "see" visual content.

[![Version](https://img.shields.io/badge/version-4.1.0-blue)](https://github.com/SlXiaMi/vision-bridge-skill)
[![License](https://img.shields.io/badge/license-MIT-green)](./LICENSE)

---

## 中文

当主模型无法直接处理图片时，本技能充当"眼睛"——把视觉内容发送给识图模型，结果以文字返回。主 AI 和识图 AI 之间用 **AI-to-AI 协议格式**（`#q @字段 >格式`）通信，高效精准。

### 快速开始

```bash
git clone https://github.com/SlXiaMi/vision-bridge-skill.git ~/.claude/skills/vision-bridge-skill
cd ~/.claude/skills/vision-bridge-skill
cp vision-bridge-config.example.json vision-bridge-config.json
# 编辑配置，填入 API 地址、密钥和模型名
python scripts/vision-bridge.py --check
```

### 基础用法

```bash
vision-bridge.py 照片.jpg --ask "#q photo @活动,地点,时间 >list" --session auto --output json
vision-bridge.py --ask "画面氛围如何？" --session auto-xxx --output json
vision-bridge.py --session auto-xxx --clear
```

| 功能 | 参数 |
|------|------|
| PDF 文档 | `--pdf-page N` / `--pdf-range M-N`（并行渲染） |
| AI-to-AI 协议 | `#q <类型> @<信息> ><格式>` + `--protocol` |
| 批量处理 | 通配符 / 多文件 / 目录 |
| 多图对比 | `--add-image` |
| 多配置 | `--profile` / `--list-profiles` |
| 图像增强 | `--enhance` |
| 流式输出 | `--stream` |
| JSON 输出 | `--output json` |

**完整文档：** 见 [README.md](./README.md)（暂未放全文，缩略版如上；完整内容见下方 English 部分的结构，或直接查看 [SKILL.md](./SKILL.md)）

---

## English

When a primary AI model cannot process images directly, this skill acts as its "eyes" — sending visual content to a vision-capable model. Primary AI and vision AI communicate via **AI-to-AI protocol** (`#q @field >format`).

### Quick Start

```bash
git clone https://github.com/SlXiaMi/vision-bridge-skill.git ~/.claude/skills/vision-bridge-skill
cd ~/.claude/skills/vision-bridge-skill
cp vision-bridge-config.example.json vision-bridge-config.json
# Edit config with your API endpoint, key, and model
python scripts/vision-bridge.py --check
```

### Basic Usage

```bash
vision-bridge.py photo.jpg --ask "#q photo @activity,location,time >list" --session auto --output json
vision-bridge.py --ask "What's the lighting like?" --session auto-xxx --output json
vision-bridge.py --session auto-xxx --clear
```

| Feature | Flag |
|---------|------|
| PDF documents | `--pdf-page N` / `--pdf-range M-N` (parallel rendering) |
| AI-to-AI protocol | `#q <type> @<info> ><format>` + `--protocol` |
| Batch processing | Wildcards / multi-file / directory |
| Multi-image | `--add-image` |
| Multi-config | `--profile` / `--list-profiles` |
| Image enhance | `--enhance` |
| Streaming | `--stream` |
| JSON output | `--output json` |

**Full docs:** See [README_EN.md](./README_EN.md) for complete documentation, or [SKILL.md](./SKILL.md) for the skill definition.

---

## License

MIT
