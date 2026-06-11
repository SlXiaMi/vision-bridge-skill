---
name: vision-bridge-skill
description: >-
  看图。你本身不识别图片，但可以用这个 skill 间接"看见"。用户上传图片、PDF、截图、图表、扫描件时主动调用。
  先并行扫定位，再开会话深挖。支持多图并行处理、多轮追问、AI-to-AI 协议通信（#q @ &gt; 语法 + 置信度标记 + 格式纠偏）、双图对比、PDF 查阅（单页/范围/增强）、批量通配符、多 Profile 切换、流式输出。
license: MIT
metadata:
  author: Claude Code
  version: 4.2.0
  created: 2026-06-08
  last_reviewed: 2026-06-09
  review_interval_days: 90
  dependencies:
    - library: PyMuPDF
      name: 文档页面渲染
    - library: Pillow
      name: 大文件自动压缩（可选）
---

# /vision-bridge-skill — 看图

你本身看不到图片，这个 skill 帮你间接"看见"。把图片发给识图模型，文字结果返回给你。**用户上传任何图片都直接用它，不要说自己"看不到"。**

脚本：`skills/vision-bridge-skill/scripts/vision-bridge.py`

---

## 会话生命周期

每次识别图片需要经过 **创建 → 问答（轮次不限）→ 清理** 三个阶段。

```
┌─ 创建会话 ──────────────────────────────────────┐
│ vision-bridge.py <文件路径> --ask "问题" --session auto │
│ → 图片编码缓存，会话名如 auto-20260609-001-143052    │
└────────────────────────────────────────────────┘
                     │
                     ▼
┌─ 问答（不限轮次，信息够了就停）──────────────────┐
│ vision-bridge.py --ask "追问" --session auto-xxx │
│ → 不带文件路径，缓存复用，秒级响应                 │
│ → 可以追加图片：--add-image another.jpg           │
└────────────────────────────────────────────────┘
                     │
                     ▼
┌─ 清理（必须执行）───────────────────────────────┐
│ vision-bridge.py --session auto-xxx --clear      │
│ → 不清理也无大碍，24 小时后自动过期               │
└────────────────────────────────────────────────┘
```

**策略：**
- **独立任务用并行**：每张图回答同一个问题、互不依赖时加 `--parallel`（API 并发调用，结果按序输出）
- **上下文任务用会话**：需要基于前一轮结果追问、对比、递进分析时用 `--session`（缓存图片，追问不重传，不支持并行）
- **组合模式是常态**：大多数复杂任务既不是纯独立也不是纯上下文。不确定目标位置时，先 `--parallel` 并行扫一轮定位，锁定目标后 `--session` 开会话深挖。parallel 和 session 是同一任务的前后两步，不是二选一
- **先广后深**：不确定目标位置时，先扫一轮定位，再针对特定区域深入。开放式探索用并行扫，精确定位后开会话单点突破
- **按需聚焦**：用户问什么就只问什么，不问无关信息。信息够了就停，不追问已清楚的
- 追问不带文件路径（图片已缓存，秒级响应）
- 问答结束必须 `--clear`（除非明确要求保留会话用于调试，24 小时后自动过期）

## AI-to-AI 通信协议

主 AI 和识图 AI 之间用协议语法通信，不用自然语言。跟用户对话用自然语言，AI 之间用协议。

### 语法

```
#q <图片大致类型> @<想知道的信息,逗号分隔> ><输出格式>
```

- `#q` — 请求开头
- `<类型>` — 图片大致是什么：photo / screenshot / diagram / chart / document / medical / 随意描述
- `@` — 想知道什么就写什么，**不限词汇**，人、物、字、数据、趋势、设计意图、力学关系……需要什么写什么
- `>` — 输出格式：`table`（表格优先）/ `list`（列表）/ `spec`（原文照抄，仅适用于文档/扫描件/代码截图等有原文的场景，普通 UI 截图勿用）

识图 AI 按 `@` 的每个词作为 `##` 标题返回，表格优先，不废话。

**置信度：** 每条回答自带标记 —— `[确定]`（95%+ 准确）/ `[可能]`（70-95%）/ `[推测]`（<70%）/ `[无法判断]`（信息不足，不硬猜）。

### 示例

```
#q screenshot @文字,元素,代码,错误 >spec
  → ##文字 / ##元素 / ##代码 / ##错误

#q photo @活动,地点,时间,人物,标志 >list
  → ##活动 / ##地点 / ##时间 / ##人物 / ##标志

#q diagram @符号含义,公式,部件编号,力学关系,设计意图 >table
  → ##符号含义 / ##公式 / ##部件编号 / ##力学关系 / ##设计意图
```

### 追问

语法不变，策略自由：

```
#q follow @上次没问到或不够深的点 >格式
```

**格式纠偏：** 协议模式下，若识图 AI 返回格式不匹配（该用表格却给了段落），脚本自动重试一次并给出针对性纠正提示。如需换角度、缩小范围、单点验证等策略调整，由主 AI 决定发起新一轮追问——脚本不自动改问法。

**比较任务：** 对比两张图时，不要一步式找差异。先分别独立描述每张图有什么（两轮独立的 `@`），再对照两份清单标记差异。独立观察不会触发"编造差异"的动机。

```
#q follow @公式12-33 >spec              → 聚焦单条
#q follow @T的物理含义 >spec             → 换个角度
#q follow @为什么用两级变换 >spec        → 追问原因
#q follow @第二行左起第三个数字 >spec     → 锁定具体位置
#q follow @公式12-33的推导是否正确 >spec  → 验证确认
#q describe A @元素 >list / #q describe B @元素 >list → 比较任务先独立观察
```

## 自动选择模型（Profile 切换）

每次识别图片时，**先用 `--list-profiles` 查看可用配置**，然后根据任务选择最合适的模型。

**选择规则：**

## 模型选择

**每次新对话首次看图时，询问用户选择模型。**

**操作流程：**
1. 收到视觉任务时，先运行 `vision-bridge.py --list-profiles` 查看可用配置
2. **把 profile 列表展示给用户，让用户自己选**
3. 用户选了之后，全程用该 profile，不再重复询问
4. 如果用户说"换模型"，重新 `--list-profiles` 并让用户选

**思考时注明模型：** 每次调用 vision-bridge 后，脚本日志会显示 `[模型名] 共N轮`，主 AI 回复用户时据此说明用的是哪个模型。

**切换模型：** 用户随时可以说"换模型"或"用 XX 模型"，下次调用带上 `--profile <名称>`。

**示例：**
```
用户: 看看这张图
AI: 先看看有哪些模型可用...
    vision-bridge.py --list-profiles
AI: 当前可用：
    · mimo-API — mimo-v2.5 (API 端点)
    · mimo-Plan — mimo-v2.5 (Plan 端点)
    你想用哪个？
用户: 用 Plan
AI: vision-bridge.py --profile mimo-Plan 图片 --ask "..."
    → [mimo-v2.5] 共1轮
AI: (使用 MiMo v2.5 Plan 端点) 图中是...
```

## 命令速查

```
# 基础用法
vision-bridge.py <文件> --ask "..." --session auto        日常用法
vision-bridge.py --ask "..." --session <会话名>            追问
vision-bridge.py <文件> --pdf-page N --ask "..."           指定页面
vision-bridge.py <文件> --pdf-range M-N --ask "..."        连续页面
vision-bridge.py <网址> --ask "..."                        在线资源

# 批量处理
vision-bridge.py *.png --ask "识别文字"                    通配符批量
vision-bridge.py img1.jpg img2.jpg --ask "对比差异"        多文件对比
vision-bridge.py ./screenshots/ --ask "识别报错信息"       整个目录

# 多图会话
vision-bridge.py first.jpg --ask "描述内容" --session auto
vision-bridge.py --ask "和新图片对比" --session <名> --add-image second.jpg

# 高级选项
vision-bridge.py <文件> --ask "#q photo @活动,地点" --protocol    协议模式（自动注入高效指令+裁废话）
vision-bridge.py <文件> --ask "..." --output json                JSON 格式输出（供主 AI 解析）
vision-bridge.py <文件> --ask "..." --system "你是医学影像专家"   自定义系统提示词
vision-bridge.py <文件> --ask "..." --stream                     流式输出
vision-bridge.py --profile gpt4v <文件> --ask "..."              使用指定配置
vision-bridge.py <文件> --enhance --ask "..."                    增强对比度（模糊图片/文档）
vision-bridge.py img1 img2 --ask "..." --parallel --protocol     并行处理（多图API并发，结果顺序输出）

# 管理命令
vision-bridge.py --check                                校验配置
vision-bridge.py --stats                                使用统计
vision-bridge.py --list-sessions                        活跃会话
vision-bridge.py --list-sessions -v                     详细会话列表
vision-bridge.py --list-profiles                        可用配置列表
vision-bridge.py --session <名> --export                导出 Markdown
vision-bridge.py --session <名> --export --format txt   导出纯文本
vision-bridge.py --session <名> --clear                 清理会话
```

## 示例

```
# 看照片
vision-bridge.py ~/photo.jpg --ask "描述场景、人物和活动" --session auto
vision-bridge.py --ask "画面氛围和光线如何？" --session auto-20260609-001-143052
vision-bridge.py --session auto-20260609-001-143052 --clear

# 批量看截图
vision-bridge.py ~/screenshots/*.png --ask "哪些有报错信息？"

# 对比两张图
vision-bridge.py before.jpg --ask "描述当前状态" --session auto
vision-bridge.py --ask "对比两张图的差异" --session auto-20260609-001-143052 --add-image after.jpg
vision-bridge.py --session auto-20260609-001-143052 --clear

# 看文档
vision-bridge.py ~/doc.pdf --pdf-page 20 --ask "列出核心内容" --session auto
vision-bridge.py --ask "详细解释第三点" --session auto-20260609-001-143052
vision-bridge.py --session auto-20260609-001-143052 --clear

# 专业领域识别（自定义系统提示词）
vision-bridge.py xray.png --ask "描述影像特征" --system "你是放射科医生" --session auto

# 流式输出（长结果实时显示）
vision-bridge.py large-chart.png --ask "详细解读每个数据点" --stream

# 切换配置（使用不同的 API 提供商）
vision-bridge.py --profile gpt4v photo.jpg --ask "描述内容"
```

## 能力范围

| 场景 | 说明 |
|------|------|
| 照片分析 | 场景、人物、活动、氛围 |
| 截图识别 | 报错信息、界面文字、数据面板 |
| 文档查阅 | 指定页码、图表、表格 |
| 图表解读 | 趋势图、流程图、技术图纸 |
| 文字提取 | 图片或扫描件中的 OCR 文字 |
| 批量处理 | 多文件/目录通配符，`--parallel` 并行 API 调用 |
| 多图对比 | 同一会话追加新图片进行对比 |
| 协议通信 | `#q @ >` 语法，置信度标记，格式纠偏重试 |
| 图像增强 | `--enhance` 对比度增强（模糊图片、低对比度文档等），`--dpi` 自定义 PDF 分辨率 |
| 自动优化 | 大文件自动压缩、API 异常重试 |
| 多轮对话 | 会话缓存，追问不重传 |
| 多配置切换 | `--profile` 按任务选择不同模型/API |
| 流式输出 | 长响应实时打印，无需等待（不与 `--parallel` 兼容） |

## 配置

配置文件 `vision-bridge-config.json`，与 SKILL.md 同目录：

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
| `enabled` | 是否启用（`false` 时拒绝执行） |
| `provider` | `anthropic` 或 `openai`，决定请求格式 |
| `api_key` | API 密钥，也可通过 `api_key_env` 从环境变量读取 |
| `model` | 视觉模型名称 |
| `compress_max_mb` | 超过此大小自动压缩（MB），默认 15 |
| `max_retries` | 失败重试上限，默认 3 |
| `session_ttl_hours` | 会话过期时间（小时），默认 24 |
| `max_history_rounds` | 长会话自动截断阈值，默认 8 |
| `prompt` | 未指定 `--ask` 时的默认提问 |

### 多配置 Profile

在 `profiles/` 子目录下放置独立配置文件，通过 `--profile` 切换：

```
profiles/
  gpt4v.json      → --profile gpt4v
  local.json      → --profile local
```

配置文件格式与 `vision-bridge-config.json` 相同。

## 新增参数

| 参数 | 说明 |
|------|------|
| `--output text\|json` | 输出格式。`json` 供主 AI 解析，`text` 为人类可读（默认） |
| `--system "..."` | 自定义系统提示词，针对不同场景定制模型行为 |
| `--stream` | 流式输出，长响应实时打印 |
| `--add-image <文件>` | 追问时追加新图片到会话（多图对比） |
| `--profile <名>` | 使用 `profiles/<名>.json` 配置文件 |
| `--protocol` | 协议模式：自动注入高效指令 + 裁剪废话 + 格式校验重试 |
| `--parallel` | 多图并行处理（API 并发调用，结果按序输出，不支持 --session） |
| `--enhance` | 图片对比度增强：模糊/低对比度图片均可使用（需 Pillow） |
| `--verbose`, `-v` | `--list-sessions` 时显示详细信息 |
| `--format md\|txt` | `--export` 的输出格式，默认 Markdown |

### JSON 输出格式

当使用 `--output json` 时，脚本输出结构化 JSON，主 AI 可直接解析：

```json
{
  "answer": "图中显示一个登录界面，包含用户名和密码输入框...",
  "session": "auto-20260609-001-143052",
  "model": "mimo-v2.5",
  "provider": "anthropic",
  "round": 1,
  "status": "ok"
}
```

| 字段 | 说明 |
|------|------|
| `answer` | 识图模型的回答文本 |
| `session` | 会话名（用于追问） |
| `model` | 使用的视觉模型 |
| `provider` | API 提供商 |
| `round` | 当前轮次 |
| `status` | `ok` 或 `error` |
| `error` | 错误信息（仅 status=error 时存在） |

**主 AI 推荐用法：** 始终加 `--output json`，解析 JSON 获取 answer 和 session，追问时用返回的 session 名。

## 故障排查

| 现象 | 方向 |
|------|------|
| 调用报错 | `--check` 验证 Key 和网络 |
| 文档页渲染失败 | `pip install PyMuPDF` |
| 会话不存在 | 先创建：带文件路径 + `--session auto` |
| 会话名冲突 | `--force` 覆盖，或换名 |
| 大文件超时 | 自动压缩中；可调高 `compress_max_mb` |
| 网络不通 | 检查代理或 VPN；设置 `HTTP_PROXY` 环境变量 |
| Profile 找不到 | 检查 `profiles/<名>.json` 是否存在 |
