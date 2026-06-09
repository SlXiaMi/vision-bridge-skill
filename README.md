# vision-bridge-skill

> [中文文档](./README_CN.md) | [English Docs](./README_EN.md)

让不支持多模态的 AI 也能"看懂"视觉内容。

Give AI models without vision the ability to "see" visual content.

[![Version](https://img.shields.io/badge/version-4.2.0-blue)](https://github.com/SlXiaMi/vision-bridge-skill)
[![License](https://img.shields.io/badge/license-MIT-green)](./LICENSE)

---

快速开始 / Quick Start:

```bash
git clone https://github.com/SlXiaMi/vision-bridge-skill.git ~/.claude/skills/vision-bridge-skill
cd ~/.claude/skills/vision-bridge-skill
cp vision-bridge-config.example.json vision-bridge-config.json
# Edit config, then verify
python scripts/vision-bridge.py --check
```

支持 / Features: 照片分析 / 截图识别 / PDF 查阅 / 图表解读 / OCR 文字提取 / 批量处理 / 多图对比 / 流式输出

Photo analysis / Screenshot recognition / PDF documents / Chart reading / OCR / Batch processing / Multi-image comparison / Streaming

## License

MIT
