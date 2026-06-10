#!/usr/bin/env python3
"""
Vision recognition script v4.2.0 — invoked by vision-bridge-skill

Capabilities: images / documents (PDF) / multi-turn sessions / compression / retry

Usage:
  # Recommended workflow
  python vision-bridge.py <file> --ask "question" --session auto
  python vision-bridge.py --ask "follow-up" --session <session-name>
  python vision-bridge.py --session <session-name> --clear

  # One-shot
  python vision-bridge.py <file> --ask "question"
  python vision-bridge.py <file>                   (default full description)
  python vision-bridge.py <file> --prompt "..."

  # Documents
  python vision-bridge.py <file> --pdf-page N --ask "..."
  python vision-bridge.py <file> --pdf-range M-N --ask "..."

  # Network
  python vision-bridge.py <URL> --ask "..."

  # Tools
  python vision-bridge.py --check
  python vision-bridge.py --stats
  python vision-bridge.py --list-sessions
  python vision-bridge.py --session <name> --export / --status / --clear
  python vision-bridge.py --stats
  python vision-bridge.py --session auto --ask "..." photo.jpg
"""

import json
import sys
import os
import io
import time
import base64
import shutil
import tempfile
import mimetypes
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

# 强制 UTF-8，解决 Windows 终端中文乱码
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# ── 常量 ──────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
SKILL_DIR = SCRIPT_DIR.parent
SESSION_DIR = SKILL_DIR / "sessions"


def find_config(profile: str = ""):
    """查找配置文件，支持 profile 切换"""
    if profile:
        # profiles 目录下的独立配置
        candidates = [
            SKILL_DIR / "profiles" / f"{profile}.json",
            Path.home() / ".claude" / "skills" / "vision-bridge-skill" / "profiles" / f"{profile}.json",
        ]
    else:
        candidates = [
            SKILL_DIR / "vision-bridge-config.json",
            Path.home() / ".claude" / "skills" / "vision-bridge-skill" / "vision-bridge-config.json",
        ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


CONFIG_PATH = find_config()

# ── 代理支持 ──────────────────────────────────────
def setup_proxy():
    """根据环境变量自动配置代理（urllib 默认不读 HTTP_PROXY）"""
    http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
    https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if http_proxy or https_proxy:
        proxy_handler = urllib_request.ProxyHandler({
            "http": http_proxy or "",
            "https": https_proxy or "",
        })
        opener = urllib_request.build_opener(proxy_handler)
        urllib_request.install_opener(opener)

IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".bmp", ".svg", ".ico", ".tiff", ".tif",
}
PDF_EXTENSIONS = {".pdf"}


def log(msg):
    safe_print(f"  {msg}", to_stderr=True)


def safe_print(text: str, to_stderr: bool = False):
    """打印，自动处理 Windows GBK 编码"""
    dest = sys.stderr if to_stderr else sys.stdout
    try:
        print(text, file=dest)
    except UnicodeEncodeError:
        try:
            print(text.encode('utf-8', errors='replace').decode('utf-8', errors='replace'), file=dest)
        except:
            print(text.encode('ascii', errors='replace').decode('ascii'), file=dest)


def log_conversation(round_num: int, question: str, answer: str):
    """将对话写入会话文件，终端不显示"""
    pass


def log_cleanup(session: str):
    """清理确认"""
    pass


def log_model_info(config, profile=""):
    """模型信息"""
    pass


def json_output(answer: str, session: str = "", model: str = "", provider: str = "",
                round_num: int = 0, status: str = "", error: str = ""):
    """输出 JSON 格式结果（供主 AI 解析）"""
    # 自动检测错误：所有错误消息都以 "[" 开头
    if not status:
        if answer.startswith("["):
            status = "error"
            if not error:
                error = answer
        else:
            status = "ok"
    obj = {
        "answer": answer,
        "session": session,
        "model": model,
        "provider": provider,
        "round": round_num,
        "status": status,
    }
    if error:
        obj["error"] = error
    safe_print(json.dumps(obj, ensure_ascii=False))


# ── 协议模式配置 ──────────────────────────────────
PROTOCOL_SYSTEM = (
    "AI-to-AI protocol mode. "
    "Respond ONLY with the requested markdown format (tables, lists, code blocks). "
    "No greetings. No 'as shown in the figure'. No 'in summary'. "
    "No explanations unless explicitly asked. "
    "Be terse and precise. Every word must carry information."
)

FILLER_PATTERNS = [
    r'^[总综][上述]+[,，].*$',     # 综上所述/总之
    r'^如图[所]?示[,，]?.*$',        # 如图所示
    r'^[以综][上][所述]*[,，].*$',    # 以上/综上
    r'^.*核心结论[是为].*$',          # 核心结论是
    r'^[整总][体]*[来而]言[,，]?.*$', # 整体而言
]


def trim_response(text: str) -> str:
    """去噪：裁掉 AI 惯用的废话开头和结尾"""
    import re as _re
    lines = text.strip().split('\n')
    # 去头
    while lines and any(_re.match(p, lines[0]) for p in FILLER_PATTERNS):
        lines.pop(0)
    # 去尾
    while lines and any(_re.match(p, lines[-1]) for p in FILLER_PATTERNS):
        lines.pop()
    return '\n'.join(lines)


def effective_system(user_system: str, protocol: bool) -> str:
    """合并用户 system prompt 和协议模式 system prompt"""
    if protocol:
        return f"{PROTOCOL_SYSTEM}\n{user_system}" if user_system else PROTOCOL_SYSTEM
    return user_system


def finalize_answer(result: str, protocol: bool) -> str:
    """对 API 返回结果做后处理"""
    if protocol:
        result = trim_response(result)
    return result


def retry_protocol(result: str, ask: str, messages: list, config: dict, api_key: str,
                   provider: str, system: str) -> tuple[str, bool]:
    """协议格式不匹配时自动重试一次。返回 (result, did_retry)"""
    if not ask or not validate_protocol(result, ask):
        log("协议格式不匹配，自动重试...")
        messages.append({"role": "user", "content": [{
            "type": "text",
            "text": "Response did not match requested format. Return ONLY the requested markdown format (table/list), no explanations, no summaries."
        }]})
        # 重试时不 stream
        if provider in ("anthropic", "mimo"):
            retry_result = call_anthropic_api(config, api_key, messages, system=system, stream=False)
        elif provider in ("openai",):
            retry_result = call_openai_api(config, api_key, messages, system=system, stream=False)
        else:
            return result, False
        return retry_result, True
    return result, False


# ── 配置 ──────────────────────────────────────────
def load_config(profile: str = ""):
    path = find_config(profile) if profile else CONFIG_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"error": f"无法加载配置 {path}: {e}"}


def get_api_key(config):
    if config.get("api_key", ""):
        return config["api_key"]
    env_key = config.get("api_key_env", "")
    if env_key and os.environ.get(env_key):
        return os.environ[env_key]
    return os.environ.get("ANTHROPIC_AUTH_TOKEN", "")


def is_image_file(file_path: str) -> bool:
    ext = Path(file_path).suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return True
    mime, _ = mimetypes.guess_type(file_path)
    return mime is not None and mime.startswith("image/")


def is_pdf_file(file_path: str) -> bool:
    return Path(file_path).suffix.lower() in PDF_EXTENSIONS


# ── 动态超时 ──────────────────────────────────────
def calc_timeout(data_size_bytes: int) -> int:
    mb = data_size_bytes / (1024 * 1024)
    if mb < 1:
        return 60
    elif mb < 5:
        return 120
    elif mb < 15:
        return 180
    else:
        return 300


# ── 图片压缩 ──────────────────────────────────────
def compress_image(file_path: str, max_mb: float = 15) -> tuple[bytes, str]:
    try:
        from PIL import Image
    except ImportError:
        log("Pillow 未安装，跳过压缩（pip install Pillow）")
        with open(file_path, "rb") as f:
            return f.read(), Path(file_path).suffix.lower().lstrip(".")

    img = Image.open(file_path)
    original_size = os.path.getsize(file_path)
    mb = original_size / (1024 * 1024)
    if mb <= max_mb:
        with open(file_path, "rb") as f:
            return f.read(), Path(file_path).suffix.lower().lstrip(".")

    log(f"图片 {mb:.1f}MB，超过 {max_mb}MB，自动压缩中...")
    w, h = img.size
    long_side = max(w, h)
    if long_side > 2048:
        ratio = 2048 / long_side
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    if img.mode in ("RGBA", "P", "LA"):
        if img.mode == "P":
            img = img.convert("RGBA")
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "RGBA":
            background.paste(img, mask=img.split()[3])
        else:
            background.paste(img)
        img = background
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    compressed = buf.getvalue()
    new_mb = len(compressed) / (1024 * 1024)
    log(f"压缩完成: {mb:.1f}MB → {new_mb:.1f}MB")
    return compressed, "jpeg"


def encode_image_base64(file_path: str, config: dict) -> tuple[str, str]:
    compress_threshold = config.get("compress_max_mb", 15)
    try:
        image_bytes, fmt = compress_image(file_path, max_mb=compress_threshold)
    except Exception as e:
        log(f"压缩异常，回退原始读取: {e}")
        with open(file_path, "rb") as f:
            image_bytes = f.read()
            fmt = Path(file_path).suffix.lower().lstrip(".")
    mime_map = {
        "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp",
        "svg": "image/svg+xml", "ico": "image/x-icon",
        "tiff": "image/tiff", "tif": "image/tiff",
    }
    media_type = mime_map.get(fmt.lower(), "image/jpeg")
    data = base64.standard_b64encode(image_bytes).decode("utf-8")
    return data, media_type


# ── 图片增强 ──────────────────────────────────────
def enhance_image(image_bytes: bytes) -> bytes:
    """增强图片对比度，使文字更清晰（Pillow 可选）"""
    try:
        from PIL import Image, ImageOps, ImageEnhance
    except ImportError:
        log("Pillow 未安装，跳过图像增强")
        return image_bytes
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.autocontrast(img, cutoff=2)
        img = ImageEnhance.Contrast(img).enhance(1.15)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        enhanced = buf.getvalue()
        log(f"图像增强完成: {len(image_bytes)/1024:.0f}KB → {len(enhanced)/1024:.0f}KB")
        return enhanced
    except Exception as e:
        log(f"增强失败，保留原图: {e}")
        return image_bytes


# ── 协议验证 ──────────────────────────────────────
def validate_protocol(response: str, ask: str) -> bool:
    """验证识图 AI 是否按协议格式返回"""
    if not ask:
        return True  # 没有协议要求，跳过验证
    if ">table" in ask:
        # 检查是否有 Markdown 表格行
        return any(line.strip().startswith("|") for line in response.split("\n"))
    if ">list" in ask:
        return any(line.strip().startswith("- ") or line.strip().startswith("* ") for line in response.split("\n"))
    if ">spec" in ask:
        # spec 模式：密度检查（行均字符数 > 30，不能太短）
        lines = [l for l in response.split("\n") if l.strip()]
        return len(lines) >= 2
    return True  # 无特定格式要求


# ── PDF 处理 ──────────────────────────────────────
def pdf_page_to_base64(pdf_path: str, page: int, dpi: int = 200,
                       enhance: bool = False) -> tuple[str, str]:
    try:
        import fitz
    except ImportError:
        raise RuntimeError("需要 PyMuPDF: pip install PyMuPDF")
    doc = fitz.open(pdf_path)
    try:
        if page < 1 or page > len(doc):
            raise ValueError(f"页码 {page} 超出范围 (1-{len(doc)})")
        pix = doc[page - 1].get_pixmap(dpi=dpi)
        img_bytes = pix.tobytes("png")
        if enhance:
            img_bytes = enhance_image(img_bytes)
        return base64.standard_b64encode(img_bytes).decode("utf-8"), "image/png"
    finally:
        doc.close()


def _render_single_page(pdf_path: str, page: int, dpi: int, enhance: bool) -> tuple[int, str, str]:
    """渲染单页 PDF（供并行调用），返回 (页码, base64, mime)"""
    try:
        import fitz
    except ImportError:
        raise RuntimeError("需要 PyMuPDF: pip install PyMuPDF")
    doc = fitz.open(pdf_path)  # 每个线程独立句柄（fitz 非线程安全）
    try:
        pix = doc[page - 1].get_pixmap(dpi=dpi)
        img_bytes = pix.tobytes("png")
        if enhance:
            img_bytes = enhance_image(img_bytes)
        return page, base64.standard_b64encode(img_bytes).decode("utf-8"), "image/png"
    finally:
        doc.close()


def pdf_range_to_base64_list(pdf_path: str, start: int, end: int, dpi: int = 200,
                              enhance: bool = False) -> list[tuple[str, str]]:
    """渲染 PDF 页码范围，并行处理"""
    try:
        import fitz
    except ImportError:
        raise RuntimeError("需要 PyMuPDF: pip install PyMuPDF")
    # 先验证页码范围
    doc = fitz.open(pdf_path)
    total = len(doc)
    doc.close()
    if start < 1 or end > total:
        raise ValueError(f"页码范围 {start}-{end} 超出范围 (1-{total})")

    pages = list(range(start, end + 1))
    if len(pages) == 1:
        # 单页直接渲染
        _, b64, mime = _render_single_page(pdf_path, pages[0], dpi, enhance)
        return [(b64, mime)]

    # 并行渲染（最多 4 个线程）
    workers = min(4, len(pages))
    log(f"并行渲染 {len(pages)} 页 ({workers} 线程)...")
    results_map = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_render_single_page, pdf_path, p, dpi, enhance): p for p in pages}
        for future in as_completed(futures):
            p, b64, mime = future.result()
            results_map[p] = (b64, mime)

    return [results_map[p] for p in pages]


# ── 会话管理 ──────────────────────────────────────
def session_path(name: str) -> Path:
    return SESSION_DIR / name


def session_meta_path(name: str) -> Path:
    return session_path(name) / "meta.json"


def session_image_path(name: str) -> Path:
    return session_path(name) / "image.b64"


def session_exists(name: str) -> bool:
    return session_meta_path(name).exists()


def save_session(name: str, images: list = None, image_b64: str = "",
                 media_type: str = "", file_name: str = "",
                 messages: list = None, config: dict = None):
    """创建或更新会话。支持多图（images 列表）或单图（image_b64 兼容旧格式）"""
    messages = messages or []
    config = config or {}
    sp = session_path(name)
    sp.mkdir(parents=True, exist_ok=True)

    # 统一为 images 列表格式
    if images is None:
        images = []
        if image_b64:
            images.append({"b64": image_b64, "media_type": media_type, "file_name": file_name})

    # 图片数据保存到 image.b64（兼容旧格式：取第一张；多图用 JSON）
    img_path = session_image_path(name)
    if not img_path.exists():
        if len(images) == 1:
            img_path.write_text(images[0]["b64"], encoding="utf-8")
        else:
            img_path.write_text(json.dumps(images), encoding="utf-8")

    # 保持首次创建时间不变
    existing_created = None
    mp = session_meta_path(name)
    if mp.exists():
        try:
            existing_created = json.loads(mp.read_text(encoding="utf-8")).get("created")
        except Exception:
            pass

    meta = {
        "media_type": images[0]["media_type"] if images else media_type,
        "file_name": file_name or (images[0]["file_name"] if images else ""),
        "images": images,
        "created": existing_created or datetime.now(timezone.utc).isoformat(),
        "updated": datetime.now(timezone.utc).isoformat(),
        "rounds": len([m for m in messages if m["role"] == "user"]),
        "messages": messages,
        "config_snapshot": {
            "model": config.get("model", ""),
            "provider": config.get("provider", ""),
        },
    }
    session_meta_path(name).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def load_session(name: str) -> dict:
    """加载会话，返回 {images, image_b64, media_type, messages, ...}"""
    if not session_exists(name):
        raise FileNotFoundError(f"会话 '{name}' 不存在")
    meta = json.loads(session_meta_path(name).read_text(encoding="utf-8"))
    img_raw = session_image_path(name).read_text(encoding="utf-8").strip()

    # 兼容：image.b64 可能是纯 base64（单图）或 JSON 数组（多图）
    if "images" in meta and meta["images"]:
        # 新格式：meta.json 中已有 images 列表
        pass
    else:
        # 旧格式：从 image.b64 和 meta 中恢复
        try:
            images = json.loads(img_raw)
            if isinstance(images, list):
                meta["images"] = images
            else:
                raise ValueError
        except (json.JSONDecodeError, ValueError):
            meta["images"] = [{"b64": img_raw,
                               "media_type": meta.get("media_type", "image/png"),
                               "file_name": meta.get("file_name", "")}]

    # 保持向后兼容：image_b64 取第一张
    meta["image_b64"] = meta["images"][0]["b64"] if meta["images"] else img_raw
    return meta


def delete_session(name: str):
    """删除会话目录"""
    sp = session_path(name)
    if sp.exists():
        shutil.rmtree(sp)


def list_sessions() -> list[str]:
    """列出所有活跃会话名"""
    if not SESSION_DIR.exists():
        return []
    return [d.name for d in SESSION_DIR.iterdir() if d.is_dir() and session_meta_path(d.name).exists()]


def cleanup_expired_sessions(ttl_hours: int = 24) -> int:
    """清理过期会话"""
    if not SESSION_DIR.exists():
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)
    removed = 0
    for name in list_sessions():
        try:
            meta = json.loads(session_meta_path(name).read_text(encoding="utf-8"))
            last_active = meta.get("updated") or meta.get("created") or "2000-01-01T00:00:00+00:00"
            last_time = datetime.fromisoformat(last_active)
            if last_time < cutoff:
                delete_session(name)
                removed += 1
        except Exception:
            pass
    return removed


def auto_session_name() -> str:
    """自动生成会话名，含时间戳后缀防并发冲突"""
    now = datetime.now()
    today = now.strftime("%Y%m%d")
    existing = [n for n in list_sessions() if n.startswith(f"auto-{today}")]
    seq = len(existing) + 1
    ts = now.strftime("%H%M%S")
    return f"auto-{today}-{seq:03d}-{ts}"


def is_url(path: str) -> bool:
    """判断是否为 HTTP/HTTPS URL"""
    try:
        parsed = urlparse(path)
        return parsed.scheme in ("http", "https")
    except Exception:
        return False


def download_url(url: str) -> str:
    """下载 URL 到临时文件，返回路径"""
    log(f"下载: {url}")
    req = urllib_request.Request(url, headers={"User-Agent": "vision-bridge-skill/4.2.0"})
    try:
        with urllib_request.urlopen(req, timeout=30) as resp:
            data = resp.read()
    except Exception as e:
        raise RuntimeError(f"下载失败: {e}")

    # 从 URL 或 Content-Type 推断扩展名
    ext = ".jpg"
    content_type = ""
    try:
        content_type = resp.headers.get("Content-Type", "")
    except Exception:
        pass
    if "png" in content_type:
        ext = ".png"
    elif "webp" in content_type:
        ext = ".webp"
    elif "gif" in content_type:
        ext = ".gif"
    else:
        parsed = urlparse(url)
        path_ext = Path(parsed.path).suffix.lower()
        if path_ext in IMAGE_EXTENSIONS:
            ext = path_ext

    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    tmp.write(data)
    tmp.close()
    log(f"下载完成: {len(data)/1024:.0f}KB → {tmp.name}")
    return tmp.name


def export_session(name: str, fmt: str = "md") -> str:
    """导出会话对话，支持 md/txt 格式"""
    if not session_exists(name):
        return f"会话 '{name}' 不存在"
    session = load_session(name)

    if fmt == "md":
        return _export_session_md(name, session)
    return _export_session_txt(name, session)


def _export_session_txt(name: str, session: dict) -> str:
    """纯文本格式"""
    lines = [
        f"会话: {name}",
        f"图片: {session.get('file_name', '?')}",
        f"模型: {session.get('config_snapshot', {}).get('model', '?')}",
        f"创建: {session['created'][:19]}",
        f"轮次: {session['rounds']}",
        "=" * 60,
    ]
    for msg in session["messages"]:
        role = {"user": "问", "assistant": "答"}.get(msg["role"], msg["role"])
        content = msg.get("content", "")
        if isinstance(content, list):
            text_parts = [c["text"] for c in content if c.get("type") == "text"]
            content = "\n".join(text_parts)
        lines.append(f"\n[{role}]: {content}")
    return "\n".join(lines)


def _export_session_md(name: str, session: dict) -> str:
    """Markdown 格式"""
    lines = [
        f"# 视觉识别会话: {name}",
        "",
        "| 属性 | 值 |",
        "|------|-----|",
        f"| 图片 | `{session.get('file_name', '?')}` |",
        f"| 模型 | `{session.get('config_snapshot', {}).get('model', '?')}` |",
        f"| 创建 | {session['created'][:19]} |",
        f"| 轮次 | {session['rounds']} |",
        "",
        "---",
        "",
    ]
    for i, msg in enumerate(session["messages"]):
        role = msg["role"]
        content = msg.get("content", "")
        if isinstance(content, list):
            text_parts = [c["text"] for c in content if c.get("type") == "text"]
            content = "\n".join(text_parts)
        if role == "user":
            lines.append(f"## ❓ 问题 {i // 2 + 1}")
            lines.append("")
            lines.append(content)
        else:
            lines.append(f"## 💡 回答")
            lines.append("")
            lines.append(content)
        lines.append("")
    return "\n".join(lines)


def get_stats():
    """统计使用数据"""
    if not SESSION_DIR.exists():
        return {"total_sessions": 0, "total_rounds": 0, "active_sessions": 0}

    sessions = []
    total_rounds = 0
    for name in list_sessions():
        try:
            # 只读 meta.json，避免加载大图片的 base64
            meta = json.loads(session_meta_path(name).read_text(encoding="utf-8"))
            total_rounds += meta.get("rounds", 0)
            sessions.append({
                "name": name,
                "file": meta.get("file_name", "?"),
                "rounds": meta.get("rounds", 0),
                "created": meta.get("created", "")[:19],
            })
        except Exception:
            pass

    # 估算磁盘占用
    total_size = 0
    if SESSION_DIR.exists():
        for d in SESSION_DIR.iterdir():
            if d.is_dir():
                for f in d.iterdir():
                    try:
                        total_size += f.stat().st_size
                    except Exception:
                        pass

    return {
        "total_sessions_ever": len(list_sessions()),
        "total_rounds": total_rounds,
        "disk_mb": round(total_size / (1024 * 1024), 1),
        "sessions": sessions,
    }


# ── 消息构建 ──────────────────────────────────────
def build_messages(image_b64: str, media_type: str, text: str,
                   history: list = None) -> list:
    """构建 API messages 数组，支持会话历史"""
    messages = list(history) if history else []
    content = []
    if image_b64:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": image_b64},
        })
    content.append({"type": "text", "text": text})
    messages.append({"role": "user", "content": content})
    return messages


def truncate_history(messages: list, max_rounds: int = 8) -> list:
    """长会话截断：保留首轮上下文 + 最近 N 轮，中间用摘要代替"""
    if not messages or len(messages) <= max_rounds * 2:
        return messages

    # 保留首轮（user + assistant）
    keep_head = 2
    # 保留最近 N-1 轮
    keep_tail = (max_rounds - 1) * 2

    head = messages[:keep_head]
    tail = messages[-keep_tail:] if keep_tail > 0 else []

    # 中间插入摘要
    skipped = (len(messages) - keep_head - len(tail)) // 2
    summary = {"role": "user", "content": [
        {"type": "text", "text": f"[中间 {skipped} 轮对话已截断以节省 token。继续当前问题。]"}
    ]}
    summary_assist = {"role": "assistant", "content": "[已截断]"}

    truncated = head + [summary, summary_assist] + tail
    log(f"会话截断: {len(messages)//2}轮 → {len(truncated)//2}轮（节省 {skipped} 轮）")
    return truncated


# ── API 调用（带重试） ────────────────────────────
def _handle_http_error(e) -> tuple:
    """统一的 HTTP 错误处理，返回 (message, should_retry)"""
    code = e.code
    err_body = ""
    try:
        err_body = e.read().decode("utf-8")
    except Exception:
        pass
    if code == 429:
        return f"[限流 {code}] {err_body}", True
    if code >= 500:
        return f"[服务器错误 {code}] {err_body}", True
    return f"[API 错误 {code}] {err_body}", False


def api_request_with_retry(fn, max_retries: int = 3) -> str:
    last_error = ""
    for attempt in range(1, max_retries + 2):
        try:
            result, should_retry = fn()
            if not should_retry:
                return result
            last_error = result
        except Exception as e:
            last_error = str(e)
            should_retry = True
        if attempt <= max_retries and should_retry:
            wait = 2 ** (attempt - 1)
            log(f"[重试 {attempt}/{max_retries}] {last_error[:80]}，{wait}秒后重试...")
            time.sleep(wait)
    return f"[重试耗尽] {last_error}"


def _parse_sse_lines(resp) -> str:
    """解析 SSE 流式响应，逐块打印并返回完整文本"""
    collected = []
    for raw_line in resp:
        line = raw_line.decode("utf-8").strip()
        if not line or line.startswith(":"):
            continue
        if line.startswith("data: "):
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                event = json.loads(data)
                # OpenAI 格式
                delta = event.get("choices", [{}])[0].get("delta", {})
                chunk = delta.get("content", "")
                if chunk:
                    print(chunk, end="", flush=True)
                    collected.append(chunk)
                    continue
                # Anthropic 格式
                if event.get("type") == "content_block_delta":
                    chunk = event.get("delta", {}).get("text", "")
                    if chunk:
                        print(chunk, end="", flush=True)
                        collected.append(chunk)
            except (json.JSONDecodeError, KeyError, IndexError):
                pass
    print()  # 换行
    return "".join(collected)


def call_anthropic_api(config, api_key, messages, body_size_hint: int = 0,
                       system: str = "", stream: bool = False) -> str:
    url = config["api_base_url"].rstrip("/") + "/v1/messages"
    payload = {
        "model": config["model"],
        "max_tokens": config.get("max_tokens", 4096),
        "messages": messages,
    }
    if system:
        payload["system"] = system
    if stream:
        payload["stream"] = True
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    max_retries = config.get("max_retries", 3)

    def do_request():
        req = urllib_request.Request(url, data=body, headers=headers, method="POST")
        try:
            timeout = calc_timeout(body_size_hint or len(body))
            resp = urllib_request.urlopen(req, timeout=timeout)
            if stream:
                result = _parse_sse_lines(resp)
                resp.close()
                return result or "[空响应]", False
            else:
                with resp:
                    result = json.loads(resp.read().decode("utf-8"))
                if "content" in result and len(result["content"]) > 0:
                    for block in result["content"]:
                        if block.get("type") == "text" and block.get("text"):
                            return block["text"], False
                    last = result["content"][-1]
                    return last.get("text", json.dumps(result, ensure_ascii=False)), False
                return json.dumps(result, ensure_ascii=False), False
        except HTTPError as e:
            return _handle_http_error(e)
        except URLError as e:
            return f"[网络错误] {e.reason}", True
        except Exception as e:
            return f"[未知错误] {e}", False

    return api_request_with_retry(do_request, max_retries)


def call_openai_api(config, api_key, messages, body_size_hint: int = 0,
                    system: str = "", stream: bool = False) -> str:
    url = config["api_base_url"].rstrip("/") + "/chat/completions"
    # 转换消息格式（OpenAI 用 image_url）
    converted = []
    # 系统提示词作为第一条消息
    if system:
        converted.append({"role": "system", "content": system})
    for m in messages:
        if m["role"] == "user" and isinstance(m["content"], list):
            parts = []
            for c in m["content"]:
                if c["type"] == "image":
                    parts.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{c['source']['media_type']};base64,{c['source']['data']}"},
                    })
                else:
                    parts.append(c)
            converted.append({"role": "user", "content": parts})
        else:
            converted.append(m)

    payload = {
        "model": config["model"],
        "max_tokens": config.get("max_tokens", 4096),
        "messages": converted,
    }
    if stream:
        payload["stream"] = True
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "content-type": "application/json",
    }
    max_retries = config.get("max_retries", 3)

    def do_request():
        req = urllib_request.Request(url, data=body, headers=headers, method="POST")
        try:
            timeout = calc_timeout(body_size_hint or len(body))
            resp = urllib_request.urlopen(req, timeout=timeout)
            if stream:
                result = _parse_sse_lines(resp)
                resp.close()
                return result or "[空响应]", False
            else:
                with resp:
                    result = json.loads(resp.read().decode("utf-8"))
                if "choices" in result and len(result["choices"]) > 0:
                    return result["choices"][0]["message"]["content"], False
                return json.dumps(result, ensure_ascii=False), False
        except HTTPError as e:
            return _handle_http_error(e)
        except URLError as e:
            return f"[网络错误] {e.reason}", True
        except Exception as e:
            return f"[未知错误] {e}", False

    return api_request_with_retry(do_request, max_retries)


# ── 配置校验 ──────────────────────────────────────
def check_config(config, api_key):
    provider = config.get("provider", "anthropic").lower()
    url = config["api_base_url"].rstrip("/")
    if provider in ("anthropic", "mimo"):
        url += "/v1/messages"
        body = json.dumps({
            "model": config["model"],
            "max_tokens": 1,
            "messages": [{"role": "user", "content": [{"type": "text", "text": "ping"}]}],
        }).encode("utf-8")
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
    else:
        # 先尝试 GET /v1/models，若 404 则回退到 POST /v1/chat/completions
        models_url = url + "/v1/models"
        body = None
        headers = {"Authorization": f"Bearer {api_key}"}
        req = urllib_request.Request(models_url, data=None, headers=headers, method="GET")
        try:
            urllib_request.urlopen(req, timeout=15)
            return True, "配置有效"
        except HTTPError as e:
            if e.code == 404:
                url = url + "/v1/chat/completions"
                body = json.dumps({
                    "model": config["model"],
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "ping"}],
                }).encode("utf-8")
                headers["content-type"] = "application/json"
            else:
                msg, _ = _handle_http_error(e)
                return False, msg
        except URLError as e:
            return False, f"网络不可达: {e.reason}"
        except Exception as e:
            return False, f"校验异常: {e}"
    req = urllib_request.Request(url, data=body, headers=headers, method="POST" if body else "GET")
    try:
        urllib_request.urlopen(req, timeout=15)
        return True, "配置有效"
    except HTTPError as e:
        msg, _ = _handle_http_error(e)
        return False, msg
    except URLError as e:
        return False, f"网络不可达: {e.reason}"
    except Exception as e:
        return False, f"校验异常: {e}"


# ── 主入口 ────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Vision recognition v4.2.0")
    parser.add_argument("--version", action="version", version="vision-bridge-skill v4.2.0")
    parser.add_argument("file_path", nargs="*", help="File path(s), directory, or HTTP URL")
    parser.add_argument("--prompt", default="", help="Custom prompt (legacy)")
    parser.add_argument("--ask", default="", help="Targeted question")
    parser.add_argument("--session", default="", help="Session name (auto=auto-generated)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing session")
    parser.add_argument("--status", action="store_true", help="Show session status")
    parser.add_argument("--list-sessions", action="store_true", help="List active sessions")
    parser.add_argument("--clear", action="store_true", help="Delete named session")
    parser.add_argument("--export", action="store_true", help="Export session as text")
    parser.add_argument("--stats", action="store_true", help="Show usage statistics")
    parser.add_argument("--profile", default="", help="Switch config profile")
    parser.add_argument("--pdf-page", type=int, help="Document page number")
    parser.add_argument("--pdf-range", help="Document page range (e.g. 20-25)")
    parser.add_argument("--dpi", type=int, default=200, help="Render DPI (default 200)")
    parser.add_argument("--no-compress", action="store_true", help="Skip auto-compression")
    parser.add_argument("--check", action="store_true", help="Validate config")
    # 新增参数
    parser.add_argument("--system", default="", help="System prompt for the vision model")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output for --list-sessions")
    parser.add_argument("--format", choices=["md", "txt"], default="md", help="Export format (default: md)")
    parser.add_argument("--stream", action="store_true", help="Stream response in real-time")
    parser.add_argument("--add-image", default="", help="Add image to existing session (follow-up)")
    parser.add_argument("--list-profiles", action="store_true", help="List available config profiles")
    parser.add_argument("--output", choices=["text", "json"], default="text", help="Output format (text or json)")
    parser.add_argument("--protocol", action="store_true", help="AI-to-AI protocol mode: compact, table-first, no filler")
    parser.add_argument("--enhance", action="store_true", help="Enhance PDF image contrast for readability (Pillow required)")
    args = parser.parse_args()

    # ── --profile 配置切换 ──────────────────────────
    if args.profile:
        log(f"使用配置 profile: {args.profile}")

    # ── 代理自动配置 ────────────────────────────────
    setup_proxy()

    # ── 自动清理过期会话 ──────────────────────────
    config = load_config(args.profile)
    if "error" not in config:
        ttl = config.get("session_ttl_hours", 24)
        removed = cleanup_expired_sessions(ttl)
        active_count = len(list_sessions())
        if removed:
            log(f"已清理 {removed} 个过期会话，当前活跃 {active_count}")
    # ── enabled 检查（管理命令除外） ──────────────────
    is_management_cmd = args.check or args.stats or args.list_sessions or args.export or args.clear or args.status
    if "error" not in config and not config.get("enabled", True) and not is_management_cmd:
        print("错误: 视觉识别已在配置中禁用 (enabled: false)", file=sys.stderr)
        sys.exit(1)

    # ── 配置校验模式 ──────────────────────────────
    if args.check:
        config = load_config(args.profile)
        if "error" in config:
            print(f"✗ {config['error']}", file=sys.stderr)
            sys.exit(1)
        api_key = get_api_key(config)
        if not api_key:
            print("✗ 未配置 API Key", file=sys.stderr)
            sys.exit(1)
        print(f"  检查配置: {config['api_base_url']} / {config['model']}", file=sys.stderr)
        ok, msg = check_config(config, api_key)
        print(f"\n{'✓' if ok else '✗'} {msg}", file=sys.stderr)
        sys.exit(0 if ok else 1)

    # ── 列出可用 profiles ──────────────────────────
    if args.list_profiles:
        profiles_dir = SKILL_DIR / "profiles"
        alt_dir = Path.home() / ".claude" / "skills" / "vision-bridge-skill" / "profiles"
        found = []
        seen_names = set()
        for d in [profiles_dir, alt_dir]:
            if d.exists():
                for f in sorted(d.iterdir()):
                    if f.suffix == ".json" and f.stem not in seen_names:
                        seen_names.add(f.stem)
                        try:
                            cfg = json.loads(f.read_text(encoding="utf-8"))
                            found.append({
                                "name": f.stem,
                                "model": cfg.get("model", "?"),
                                "provider": cfg.get("provider", "?"),
                                "url": cfg.get("api_base_url", "?"),
                            })
                        except Exception:
                            found.append({"name": f.stem, "model": "(解析失败)", "provider": "?", "url": "?"})
        if not found:
            print("没有找到 profile 配置文件")
            print(f"在 {profiles_dir} 下创建 <名称>.json 即可")
        else:
            print(f"可用 profiles ({len(found)}):")
            for p in found:
                print(f"  --profile {p['name']:12s}  {p['model']:20s}  {p['provider']:10s}  {p['url']}")
        return

    # ── 会话管理命令（不需要 file_path） ──────────
    if args.list_sessions:
        names = list_sessions()
        if not names:
            print("No active sessions")
        else:
            print(f"活跃会话 ({len(names)}):")
            for name in sorted(names):
                try:
                    # 只读 meta.json，不加载图片
                    meta = json.loads(session_meta_path(name).read_text(encoding="utf-8"))
                    rounds = meta.get("rounds", 0)
                    fname = meta.get("file_name", "?")
                    created = meta.get("created", "")[:19]
                    if args.verbose:
                        # 详细模式：显示最后追问摘要
                        msgs = meta.get("messages", [])
                        last_q = ""
                        for m in reversed(msgs):
                            if m["role"] == "user":
                                c = m.get("content", "")
                                if isinstance(c, list):
                                    c = " ".join(p.get("text", "") for p in c if p.get("type") == "text")
                                last_q = c[:50] + ("..." if len(c) > 50 else "")
                                break
                        print(f"  {name}")
                        print(f"    文件: {fname}  |  {rounds}轮  |  {created}")
                        if last_q:
                            print(f"    最后追问: {last_q}")
                    else:
                        print(f"  {name:20s}  {fname:20s}  {rounds}轮  {created}")
                except Exception:
                    print(f"  {name:20s}  (损坏)")
        return

    if args.stats:
        stats = get_stats()
        print(f"Active sessions: {stats['total_sessions_ever']}")
        print(f"Total rounds: {stats['total_rounds']}")
        print(f"Disk usage: {stats['disk_mb']} MB")
        if stats["sessions"]:
            print(f"\n{'Session':20s} {'File':25s} {'Rounds':>5s} {'Created'}")
            print("-" * 65)
            for s in stats["sessions"]:
                print(f"{s['name']:20s} {s['file'][:24]:25s} {s['rounds']:>5d} {s['created']}")
        return

    if args.export and args.session:
        print(export_session(args.session, fmt=args.format))
        return

    if args.clear and args.session:
        if session_exists(args.session):
            delete_session(args.session)
            log_cleanup(args.session)
        else:
            print(f"会话 '{args.session}' 不存在")
        return

    if args.status and args.session:
        if not session_exists(args.session):
            print(f"会话 '{args.session}' 不存在", file=sys.stderr)
            sys.exit(1)
        s = load_session(args.session)
        print(f"Session: {args.session}")
        print(f"  File: {s.get('file_name', '?')}")
        print(f"  Created: {s['created'][:19]}")
        print(f"  Updated: {s.get('updated', '?')[:19]}")
        print(f"  Rounds: {s['rounds']}")
        print(f"  Model: {s.get('config_snapshot', {}).get('model', '?')}")
        return

    # ── 自动会话名 ────────────────────────────────
    if args.session == "auto":
        args.session = auto_session_name()

    # ── 追问模式（有 --ask + --session，但无 file_path）──
    if args.ask and args.session and not args.file_path:
        if not session_exists(args.session):
            print(f"错误: 会话 '{args.session}' 不存在，请先创建: python vision-bridge.py <文件> --ask '...' --session {args.session}",
                  file=sys.stderr)
            sys.exit(1)

        session = load_session(args.session)
        history = list(session["messages"])

        # 长会话截断（超过 8 轮自动压缩）
        max_rounds = config.get("max_history_rounds", 8)
        if len(history) > max_rounds * 2:
            history = truncate_history(history, max_rounds)

        # 兼容旧格式：统一为 images 列表
        if "images" in session:
            images = list(session["images"])
        else:
            images = [{"b64": session["image_b64"], "media_type": session["media_type"],
                       "file_name": session.get("file_name", "")}]

        # --add-image: 追加新图片到会话
        if args.add_image:
            add_path = args.add_image
            if is_url(add_path):
                try:
                    add_path = download_url(add_path)
                except RuntimeError as e:
                    print(f"错误: 下载追加图片失败: {e}", file=sys.stderr)
                    sys.exit(1)
            if not os.path.isfile(add_path):
                print(f"错误: 追加图片不存在 — {args.add_image}", file=sys.stderr)
                sys.exit(1)
            cfg = load_config(args.profile)
            img_b64, img_mime = encode_image_base64(add_path, cfg)
            images.append({"b64": img_b64, "media_type": img_mime,
                           "file_name": Path(add_path).name})
            log(f"追加图片: {Path(add_path).name} (共 {len(images)} 张)")

        # 把所有图片补回第一条 user 消息
        if history and history[0]["role"] == "user":
            # 先去掉已有的图片块
            history[0]["content"] = [c for c in history[0]["content"] if c.get("type") != "image"]
            # 再插入所有图片
            for img in images:
                image_block = {
                    "type": "image",
                    "source": {"type": "base64", "media_type": img["media_type"], "data": img["b64"]},
                }
                history[0]["content"].insert(0, image_block)

        # 构建消息：历史 + 新问题
        question = args.ask
        history.append({"role": "user", "content": [{"type": "text", "text": question}]})
        messages = history

        config = load_config(args.profile)
        if "error" in config:
            print(f"错误: {config['error']}", file=sys.stderr)
            sys.exit(1)
        api_key = get_api_key(config)
        provider = config.get("provider", "anthropic").lower()

        log(f"追问: {args.session} (第{session['rounds']+1}轮)")
        log_model_info(config, args.profile)

        if provider in ("anthropic", "mimo"):
            result = call_anthropic_api(config, api_key, messages,
                                        system=effective_system(args.system, args.protocol), stream=args.stream)
        elif provider in ("openai",):
            result = call_openai_api(config, api_key, messages,
                                     system=effective_system(args.system, args.protocol), stream=args.stream)
        else:
            result = f"[配置错误] 不支持的 provider: {provider}"

        # 协议验证 + 自动重试（非 stream 模式）
        if args.protocol and not args.stream and not validate_protocol(result, args.ask):
            result, _ = retry_protocol(result, args.ask, messages, config, api_key, provider,
                                       effective_system(args.system, args.protocol))

        result = finalize_answer(result, args.protocol)

        round_num = sum(1 for m in history if m.get("role") == "user")
        log_conversation(round_num, question, result)

        # 更新会话（保存前去掉图片数据块）
        history.append({"role": "assistant", "content": result})
        save_history = [dict(m) for m in history]
        if save_history and save_history[0]["role"] == "user":
            save_history[0] = {
                "role": "user",
                "content": [c for c in save_history[0]["content"] if c.get("type") != "image"],
            }
        save_session(args.session,
                     images=images,
                     file_name=session.get("file_name", ""),
                     messages=save_history,
                     config=config)
        if args.output == "json":
            json_output(result, session=args.session, model=config.get("model", ""),
                        provider=config.get("provider", ""), round_num=session.get("rounds", 0) + 1)
        else:
            safe_print(result)
        return

    # ── 需要 file_path 的命令 ─────────────────────
    if not args.file_path:
        parser.print_help()
        sys.exit(1)

    # ── 展开文件列表（支持目录和多文件）────────────
    raw_paths = list(args.file_path)
    expanded_files = []
    for p in raw_paths:
        if os.path.isdir(p):
            # 目录：收集所有图片和 PDF
            for f in sorted(Path(p).iterdir()):
                if f.is_file() and (is_image_file(str(f)) or is_pdf_file(str(f))):
                    expanded_files.append(str(f))
        elif os.path.isfile(p) or is_url(p):
            expanded_files.append(p)
        else:
            print(f"警告: 跳过不存在的路径 — {p}", file=sys.stderr)

    if not expanded_files:
        print("错误: 没有找到可处理的文件", file=sys.stderr)
        sys.exit(1)

    # ── 加载配置 ─────────────────────────────────
    config = load_config(args.profile)
    if "error" in config:
        print(f"错误: {config['error']}", file=sys.stderr)
        sys.exit(1)
    api_key = get_api_key(config)
    if not api_key:
        print(f"错误: 未配置 API Key，请在 {CONFIG_PATH} 中设置 api_key", file=sys.stderr)
        sys.exit(1)

    provider = config.get("provider", "anthropic").lower()
    default_prompt = config.get("prompt", "请详细描述这张图片的内容。")

    # ── 会话冲突检查（批量模式下跳过，每个文件独立检查）──
    # 批量模式不指定 --session 时每个文件独立处理
    cleanup_files = []  # 需要清理的临时文件

    # ── 逐文件处理 ────────────────────────────────
    for file_idx, file_path in enumerate(expanded_files):
        if len(expanded_files) > 1:
            log(f"━━━ [{file_idx+1}/{len(expanded_files)}] {Path(file_path).name} ━━━")

        # URL 下载
        cleanup_url_file = None
        if is_url(file_path):
            try:
                tmp = download_url(file_path)
                cleanup_url_file = tmp
                cleanup_files.append(tmp)
                file_path = tmp
            except RuntimeError as e:
                print(f"错误: {e}", file=sys.stderr)
                continue

        images_to_process = []  # [(base64, media_type, label)]

        # PDF 模式
        if args.pdf_page:
            if not is_pdf_file(file_path):
                print(f"错误: --pdf-page 仅用于 PDF 文件", file=sys.stderr)
                continue
            log(f"PDF 第 {args.pdf_page} 页，渲染中...")
            b64, mime = pdf_page_to_base64(file_path, args.pdf_page, dpi=args.dpi, enhance=args.enhance)
            images_to_process.append((b64, mime, f"第{args.pdf_page}页"))

        elif args.pdf_range:
            if not is_pdf_file(file_path):
                print(f"错误: --pdf-range 仅用于 PDF 文件", file=sys.stderr)
                continue
            parts = args.pdf_range.split("-")
            if len(parts) != 2:
                print(f"错误: --pdf-range 格式应为 起始-结束，如 20-25", file=sys.stderr)
                continue
            try:
                start, end = int(parts[0]), int(parts[1])
            except ValueError:
                print(f"错误: --pdf-range 页码必须是数字，收到: {args.pdf_range}", file=sys.stderr)
                continue
            log(f"PDF 第 {start}-{end} 页，渲染中...")
            for idx, (b64, mime) in enumerate(pdf_range_to_base64_list(file_path, start, end, dpi=args.dpi, enhance=args.enhance)):
                images_to_process.append((b64, mime, f"第{start+idx}页"))

        # 普通图片模式
        elif os.path.isfile(file_path):
            if is_image_file(file_path):
                if args.no_compress:
                    with open(file_path, "rb") as f:
                        raw = base64.standard_b64encode(f.read()).decode("utf-8")
                    mime, _ = mimetypes.guess_type(file_path)
                    if not mime:
                        mime = "image/png"
                    images_to_process.append((raw, mime, Path(file_path).name))
                else:
                    image_b64, media_type = encode_image_base64(file_path, config)
                    images_to_process.append((image_b64, media_type, Path(file_path).name))
            else:
                print(f"错误: 不支持的文件格式 — {Path(file_path).name}", file=sys.stderr)
                continue
        else:
            print(f"错误: 文件不存在 — {file_path}", file=sys.stderr)
            continue

        # 会话冲突检查
        if args.session and session_exists(args.session) and not args.force:
            print(f"错误: 会话 '{args.session}' 已存在，请用 --force 覆盖或换一个名字", file=sys.stderr)
            continue

        # ── 识别每张图 ───────────────────────────
        for i, (image_b64, media_type, label) in enumerate(images_to_process):
            if len(images_to_process) > 1:
                log(f"[{i+1}/{len(images_to_process)}] {label}")

            # 确定提问文本
            if args.ask:
                question = args.ask
            elif args.prompt:
                question = args.prompt
            else:
                question = default_prompt

            # 构建 messages
            history = []
            session_b64 = image_b64
            session_mime = media_type

            if args.session and session_exists(args.session):
                session = load_session(args.session)
                history = list(session["messages"])
                max_rounds = config.get("max_history_rounds", 8)
                if len(history) > max_rounds * 2:
                    history = truncate_history(history, max_rounds)
                session_b64 = session["image_b64"]
                session_mime = session["media_type"]

            image_for_api = session_b64 if history else image_b64
            messages = build_messages(image_for_api, session_mime, question, history)

            log_model_info(config, args.profile)

            if provider in ("anthropic", "mimo"):
                result = call_anthropic_api(config, api_key, messages,
                                            system=effective_system(args.system, args.protocol), stream=args.stream)
            elif provider in ("openai",):
                result = call_openai_api(config, api_key, messages,
                                         system=effective_system(args.system, args.protocol), stream=args.stream)
            else:
                result = f"[配置错误] 不支持的 provider: {provider}"

            # 协议验证 + 自动重试（非 stream 模式）
            if args.protocol and not args.stream and not validate_protocol(result, args.ask):
                result, _ = retry_protocol(result, args.ask, messages, config, api_key, provider,
                                           effective_system(args.system, args.protocol))

            result = finalize_answer(result, args.protocol)

            round_num = sum(1 for m in messages if m.get("role") == "user")
            log_conversation(round_num, question, result)

            # 保存会话
            if args.session:
                history = list(history)
                history.append({"role": "user", "content": [{"type": "text", "text": question}]})
                history.append({"role": "assistant", "content": result})
                save_session(args.session,
                             images=[{"b64": session_b64, "media_type": session_mime,
                                      "file_name": Path(file_path).name}],
                             file_name=Path(file_path).name,
                             messages=history,
                             config=config)

            if args.output == "json":
                json_output(result, session=args.session, model=config.get("model", ""),
                            provider=config.get("provider", ""), round_num=1)
            else:
                if len(expanded_files) > 1 or len(images_to_process) > 1:
                    print(f"\n===== {label} =====")
                safe_print(result)

    # ── 临时文件清理 ──────────────────────────────
    for f in cleanup_files:
        try:
            os.unlink(f)
        except Exception:
            pass


if __name__ == "__main__":
    main()
