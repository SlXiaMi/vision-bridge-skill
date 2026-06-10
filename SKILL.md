---
name: vision-bridge-skill
description: >-
  视觉识别：看照片、截图、文档、图表、扫描件——凡是需要"眼睛"的任务都用它。
  主模型和识图模型之间用 AI-to-AI 协议通信，高密度、低废话、自带置信度。
  支持多轮自适应追问、双图对比、PDF 文档查阅、批量处理。
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

# /vision-bridge-skill — 给你的 AI 装上眼睛

你本身看不到图片。这个 skill 帮你把任何视觉内容发给识图模型，结果以文字返回。你只负责分析需求和追问，识图 AI 负责"看"。

脚本：`skills/vision-bridge-skill/scripts/vision-bridge.py`

## 什么时候用

用户提到以下任何一种情况，**直接用，不要说自己"看不到图片"**：

- 上传了照片、截图、扫描件、PDF 页面
- 说"帮我看下这张图""识别一下""这个图表什么意思"
- 问"这个位置对不对""排版有没有问题""颜色一样吗"
- 需要对比两张图、审查文档、提取表格数据

## 三步用法

```
① 发送首问（图片只编码一次）
  vision-bridge.py <文件> --ask "问题" --session auto --output json

② 追问（不限轮次，图片已缓存）
  vision-bridge.py --ask "追问" --session <上一步的session名> --output json

③ 清理
  vision-bridge.py --session <session名> --clear
```

**核心原则：** 带着目的问、策略自由、信息够了就停、结束必须清理。

## 策略

- **并行优先**：搜索范围用批量一次覆盖
- **先广后深**：不确定时先扫一轮定位，再深挖
- **按需聚焦**：用户问什么就只答什么，不画蛇添足
- **轮次不限**：根据信息充分程度自行判断

## AI-to-AI 通信协议

你和识图 AI 之间用协议语法，不用自然语言。

```
语法: #q <图片类型> @<想知道的信息> ><输出格式>

#q photo @活动,地点,时间 >list
#q diagram @符号含义,公式,设计意图 >table
#q screenshot @文字,元素,错误 >spec
#q follow @上次不够深的点 >格式
```

`@` 不限词汇，需要什么写什么。`>` 可选 `table` / `list` / `spec`。

### 回答质量

识图 AI 每条回答自带标记：

- `[确定]` — 可信，直接采信
- `[可能]` — 有一定把握，可以追问确认
- `[推测]` — 不确定，建议换方式重问
- `[无法判断]` — 信息不足，放弃此点

### 追问策略

语法不变，问法自由。一轮不理想就换：

```
#q follow @T的物理含义 >spec          → 聚焦单条
#q follow @第二行左数第三个数字 >spec  → 锁定位置
#q follow @公式推导是否正确 >spec      → 验证确认
#q follow @为什么用这个设计 >spec      → 追问原因
```

**比较任务：** 对比两张图时不要一步式找差异——先分别独立描述每张图，再对照两份清单。独立观察不会触发编造。

### 空间锚定（可选）

```
@文字 >spec x:0.1-0.5,y:0.3-0.6
```
坐标范围 0-1，相对于图片宽高。

## 能力范围

| 场景 | 怎么做 |
|------|--------|
| 照片分析 | `#q photo @活动,地点,时间,人物 >list` |
| 截图识别 | `#q screenshot @文字,元素,代码,错误 >spec` |
| PDF 查阅 | `--pdf-page N` 或 `--pdf-range M-N` |
| 图表解读 | `#q diagram @符号,公式,趋势 >table` |
| 双图对比 | `--add-image` 追加第二张图 |
| 批量处理 | 通配符或目录路径 |
| 在线图片 | 直接传 URL |

## 管理命令

```bash
vision-bridge.py --check              # 验证配置
vision-bridge.py --list-sessions      # 活跃会话
vision-bridge.py --list-profiles      # 可用模型配置
vision-bridge.py --session <名> --export  # 导出对话
vision-bridge.py --session <名> --clear   # 清理会话
vision-bridge.py --version            # 版本号
```

## 配置

`vision-bridge-config.json`（与 SKILL.md 同目录）：

```json
{
  "provider": "anthropic",
  "api_base_url": "https://your-api-endpoint.com",
  "api_key": "your-key",
  "model": "your-vision-model",
  "max_tokens": 4096,
  "compress_max_mb": 15,
  "max_retries": 3,
  "session_ttl_hours": 24,
  "max_history_rounds": 8
}
```

多模型切换：`profiles/` 目录下放配置，`--profile <名>` 使用。

## 故障排查

| 现象 | 方向 |
|------|------|
| 调用报错 | `--check` 验证 Key 和网络 |
| PDF 页面渲染失败 | `pip install PyMuPDF` |
| 网络不通 | 检查代理或 `HTTP_PROXY` 环境变量 |
| 会话名冲突 | `--force` 覆盖或换名 |
