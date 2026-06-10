# vision-bridge-skill

Give AI models without vision the ability to "see" visual content.

[![Version](https://img.shields.io/badge/version-4.2.0-blue)](https://github.com/SlXiaMi/vision-bridge-skill)
[![License](https://img.shields.io/badge/license-MIT-green)](./LICENSE)

---

## Overview

When a primary AI model (e.g., DeepSeek) cannot process images directly, this skill acts as its "eyes" — sending visual content to a vision-capable model and returning the text description back to the primary model.

**Core design:** Primary AI and vision AI communicate using an **AI-to-AI protocol format** (`#q @field >format`) — efficient and precise. Natural language for users, protocol for AIs.

---

## Quick Start

```bash
git clone https://github.com/SlXiaMi/vision-bridge-skill.git ~/.claude/skills/vision-bridge-skill
cd ~/.claude/skills/vision-bridge-skill
cp vision-bridge-config.example.json vision-bridge-config.json
# Edit vision-bridge-config.json with your API endpoint, key, and model
python scripts/vision-bridge.py --check
```

---

## Session Lifecycle

Every recognition follows **Create → Q&A (unlimited rounds) → Cleanup**:

```
Create ─ vision-bridge.py <file> --ask "question" --session auto --output json
Q&A   ─ Unlimited rounds. Stop when information is sufficient. Use protocol format.
Clean ─ vision-bridge.py --session <name> --clear (mandatory)
```

---

## Basic Usage

```bash
# Single recognition
vision-bridge.py photo.jpg --ask "#q photo @activity,location,time >list" --session auto --output json

# Multi-turn follow-up (image cached, instant response)
vision-bridge.py --ask "What's the mood and lighting?" --session auto-xxx --output json
vision-bridge.py --ask "Any text visible?" --session auto-xxx --output json

# Cleanup
vision-bridge.py --session auto-xxx --clear
```

### PDF Documents

```bash
# Single page
vision-bridge.py doc.pdf --pdf-page 20 --ask "#q diagram @symbols,formulas >table" --session auto

# Page range (parallel rendering, 4 threads)
vision-bridge.py doc.pdf --pdf-range 20-25 --ask "Summarize these pages" --session auto

# High DPI + contrast enhancement
vision-bridge.py doc.pdf --pdf-page 1 --dpi 300 --enhance --ask "#q text @text >spec"
```

### Online Resources

```bash
vision-bridge.py https://example.com/chart.png --ask "#q chart @data,trends >table"
```

---

## AI-to-AI Protocol

Primary AI and vision AI communicate using a compact protocol instead of natural language.

```
Request:  #q <image type> @<desired info> ><output format>
Response: #a + Markdown tables/lists

Example:  #q diagram @symbols,formulas,labels >table
          → Vision AI returns pure tables, no greetings, no summaries
```

`@` fields are **open-ended** — write whatever information you need. `>` specifies output format: `table` / `list` / `spec`.

```
#q photo @activity,location,time        >list
#q screenshot @text,elements,errors      >spec
#q diagram @symbols,formulas,intent      >table
```

Follow-up: `#q follow @what_was_missed_or_needs_depth >format`

### New in v4.2.0

- **Confidence Markers**: `[确定]` `[可能]` `[推测]` `[无法判断]` — the vision AI self-reports reliability, reducing false positives from 55% to near zero
- **Format-Correct Retry**: When protocol format doesn't match, auto-retry once with targeted correction hint. Strategy changes (narrower scope, different angle, verification) are left to the primary AI via new follow-ups
- **Two-Phase Observation**: Comparison tasks first describe each image independently, then cross-reference — eliminates hallucination at the source

---

## Advanced Features

### `--protocol` Mode

Auto-injects efficient system instructions + trims filler text. Auto-retries if the vision AI doesn't comply with the requested format.

```bash
vision-bridge.py chart.png --ask "#q chart @data,trends >table" --protocol --output json
```

### `--output json`

Returns structured JSON for the primary AI to parse:

```json
{"answer": "...", "session": "auto-xxx", "model": "mimo-v2.5", "round": 1, "status": "ok"}
```

### Batch Processing

```bash
vision-bridge.py ~/screenshots/*.png --ask "Which ones show errors?"
vision-bridge.py img1.jpg img2.jpg --ask "Compare differences"
vision-bridge.py ./documents/ --ask "List all chart titles"
```

### Multi-Image Comparison

```bash
vision-bridge.py before.jpg --ask "#q photo @subjects >list" --session auto
vision-bridge.py --ask "What changed?" --session auto-xxx --add-image after.jpg
vision-bridge.py --session auto-xxx --clear
```

### `--profile` Multi-Config

```
profiles/
  gpt4v.json  →  --profile gpt4v
  local.json  →  --profile local
```

```bash
vision-bridge.py --profile gpt4v photo.jpg --ask "#q photo @subjects,scene"
vision-bridge.py --list-profiles   # Show available profiles
```

### `--system` Role Setting + `--stream` + `--enhance`

```bash
vision-bridge.py xray.png --ask "#q medical @findings >spec" --system "You are a radiologist" --protocol
vision-bridge.py chart.png --ask "#q chart @data >table" --stream
vision-bridge.py blurry-doc.pdf --pdf-page 1 --enhance --ask "#q text @text >spec"
```

---

## Management Commands

```bash
vision-bridge.py --check                      # Verify configuration
vision-bridge.py --check --profile gpt4v      # Verify specific profile
vision-bridge.py --stats                      # Usage statistics
vision-bridge.py --list-sessions              # Active sessions
vision-bridge.py --list-sessions -v           # Detailed session info
vision-bridge.py --list-profiles              # Available profiles
vision-bridge.py --session <name> --status    # Session details
vision-bridge.py --session <name> --export    # Export as Markdown
vision-bridge.py --session <name> --clear     # Clean up session
vision-bridge.py --version                    # Version number
```

---

## Configuration

`vision-bridge-config.json`:

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
  "prompt": "Default question content"
}
```

| Field | Description |
|------|-------------|
| `provider` | `anthropic` or `openai` |
| `api_base_url` | API endpoint URL |
| `api_key` | API key (or use `api_key_env` for env variable) |
| `model` | Vision model name |
| `compress_max_mb` | Auto-compress above this size (MB), default 15 |
| `max_retries` | Max retry count, default 3 |
| `session_ttl_hours` | Session expiry (hours), default 24 |
| `max_history_rounds` | Auto-truncate long sessions, keep head + tail, default 8 |
| `prompt` | Default question when `--ask` is omitted |

---

## Full Parameter List

| Parameter | Description |
|-----------|-------------|
| `file_path` | File path, directory, or URL (multiple supported) |
| `--ask` | Question (protocol format recommended) |
| `--output text\|json` | Output format, default text |
| `--protocol` | Protocol mode: auto-inject + trim filler + format validation with retry |
| `--system` | System prompt / role setting |
| `--stream` | Stream output in real-time |
| `--session auto\|<name>` | Session management |
| `--add-image <file>` | Add image to existing session |
| `--profile <name>` | Switch config profile |
| `--enhance` | PDF image contrast enhancement (Pillow optional) |
| `--parallel` | Multi-image parallel API calls, results in order (no `--session`) |
| `--pdf-page N` | Specific PDF page |
| `--pdf-range M-N` | PDF page range (parallel, 4 threads) |
| `--dpi N` | Render DPI, default 200 |
| `--no-compress` | Skip compression |
| `--force` | Overwrite existing session |
| `--verbose` `-v` | Verbose output |
| `--format md\|txt` | Export format |
| `--check` | Validate configuration |
| `--stats` | Usage statistics |
| `--list-sessions` | List active sessions |
| `--list-profiles` | List available profiles |
| `--clear` | Clean up session |
| `--version` | Show version |

---

## Dependencies

```bash
pip install PyMuPDF    # PDF rendering (required)
pip install Pillow     # Compression + enhancement (optional)
```

## API Compatibility

| provider | Path | Auth | Compatible Models |
|----------|------|------|-------------------|
| `anthropic` | `/v1/messages` | `x-api-key` | Claude, MiMo |
| `openai` | `/chat/completions` | `Authorization: Bearer` | GPT-4o, DeepSeek Vision, Ollama |

---

## File Structure

```
vision-bridge-skill/
├── SKILL.md
├── README.md
├── README_EN.md
├── vision-bridge-config.json
├── vision-bridge-config.example.json
├── profiles/
│   ├── example.json
│   └── <custom>.json
├── scripts/
│   └── vision-bridge.py       # ~1400 lines
└── sessions/                  # Auto-cleaned
```

## License

MIT
