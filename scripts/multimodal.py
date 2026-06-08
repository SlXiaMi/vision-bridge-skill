#!/usr/bin/env python3
"""
Vision recognition script v3.3 — invoked by multimodal-skill

Capabilities: images / documents (PDF) / multi-turn sessions / compression / retry

Usage:
  # Recommended workflow
  python multimodal.py <file> --ask "question" --session auto
  python multimodal.py --ask "follow-up" --session <session-name>
  python multimodal.py --session <session-name> --clear

  # One-shot
  python multimodal.py <file> --ask "question"
  python multimodal.py <file>                   (default full description)
  python multimodal.py <file> --prompt "..."

  # Documents
  python multimodal.py <file> --pdf-page N --ask "..."
  python multimodal.py <file> --pdf-range M-N --ask "..."

  # Network
  python multimodal.py <URL> --ask "..."

  # Tools
  python multimodal.py --check
  python multimodal.py --stats
  python multimodal.py --list-sessions
  python multimodal.py --session <name> --export / --status / --clear
  python multimodal.py --stats
  python multimodal.py --session auto --ask "..." photo.jpg
"""

import json
import sys
import os
import io
import time
import base64
import shutil
import re
import tempfile
import mimetypes
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse


# ── 常量 ──────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
SKILL_DIR = SCRIPT_DIR.parent
SESSION_DIR = SKILL_DIR / "sessions"


def find_config():
    candidates = [
        SKILL_DIR / "multimodal-config.json",
        Path.home() / ".claude" / "skills" / "multimodal-skill" / "multimodal-config.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


CONFIG_PATH = find_config()

IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".bmp", ".svg", ".ico", ".tiff", ".tif",
}
PDF_EXTENSIONS = {".pdf"}


def log(msg):
    print(f"  {msg}", file=sys.stderr, flush=True)


def safe_print(text: str):
    """打印到 stdout，自动处理编码问题"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8', errors='replace'))


# ── 配置 ──────────────────────────────────────────
def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"error": f"无法加载配置 {CONFIG_PATH}: {e}"}


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
    except Exception:
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


# ── PDF 处理 ──────────────────────────────────────
def pdf_page_to_base64(pdf_path: str, page: int, dpi: int = 200) -> tuple[str, str]:
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
        return base64.standard_b64encode(img_bytes).decode("utf-8"), "image/png"
    finally:
        doc.close()


def pdf_range_to_base64_list(pdf_path: str, start: int, end: int, dpi: int = 200) -> list[tuple[str, str]]:
    import fitz
    doc = fitz.open(pdf_path)
    try:
        if start < 1 or end > len(doc):
            raise ValueError(f"页码范围 {start}-{end} 超出范围 (1-{len(doc)})")
        results = []
        for p in range(start, end + 1):
            pix = doc[p - 1].get_pixmap(dpi=dpi)
            img_bytes = pix.tobytes("png")
            results.append((base64.standard_b64encode(img_bytes).decode("utf-8"), "image/png"))
        return results
    finally:
        doc.close()


# ── 会话管理 ──────────────────────────────────────
def session_path(name: str) -> Path:
    return SESSION_DIR / name


def session_meta_path(name: str) -> Path:
    return session_path(name) / "meta.json"


def session_image_path(name: str) -> Path:
    return session_path(name) / "image.b64"


def session_exists(name: str) -> bool:
    return session_meta_path(name).exists()


def save_session(name: str, image_b64: str, media_type: str, file_name: str,
                 messages: list, config: dict):
    """创建或更新会话"""
    sp = session_path(name)
    sp.mkdir(parents=True, exist_ok=True)

    # 图片只在新会话时保存（追问不重写）
    img_path = session_image_path(name)
    if not img_path.exists():
        img_path.write_text(image_b64, encoding="utf-8")

    meta = {
        "media_type": media_type,
        "file_name": file_name,
        "created": session_meta_path(name).exists() and
                   json.loads(session_meta_path(name).read_text(encoding="utf-8")).get("created") or
                   datetime.now(timezone.utc).isoformat(),
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
    """加载会话，返回 {image_b64, media_type, messages, ...}"""
    if not session_exists(name):
        raise FileNotFoundError(f"会话 '{name}' 不存在")
    meta = json.loads(session_meta_path(name).read_text(encoding="utf-8"))
    img = session_image_path(name).read_text(encoding="utf-8").strip()
    meta["image_b64"] = img
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


def cleanup_expired_sessions(ttl_hours: int = 24):
    """清理过期会话"""
    if not SESSION_DIR.exists():
        return
    cutoff = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)
    removed = 0
    for name in list_sessions():
        try:
            meta = json.loads(session_meta_path(name).read_text(encoding="utf-8"))
            created = datetime.fromisoformat(meta.get("created", "2000-01-01T00:00:00+00:00"))
            if created < cutoff:
                delete_session(name)
                removed += 1
        except Exception:
            pass
    return removed


def auto_session_name() -> str:
    """自动生成会话名"""
    today = datetime.now().strftime("%Y%m%d")
    existing = [n for n in list_sessions() if n.startswith(f"auto-{today}")]
    return f"auto-{today}-{len(existing)+1:03d}"


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
    req = urllib_request.Request(url, headers={"User-Agent": "multimodal-skill/3.1"})
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


def export_session(name: str) -> str:
    """导出会话为纯文本对话"""
    if not session_exists(name):
        return f"会话 '{name}' 不存在"
    session = load_session(name)
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


def get_stats():
    """统计使用数据"""
    if not SESSION_DIR.exists():
        return {"total_sessions": 0, "total_rounds": 0, "active_sessions": 0}

    sessions = []
    total_rounds = 0
    for name in list_sessions():
        try:
            s = load_session(name)
            total_rounds += s.get("rounds", 0)
            sessions.append({
                "name": name,
                "file": s.get("file_name", "?"),
                "rounds": s.get("rounds", 0),
                "created": s.get("created", "")[:19],
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


# ── API 调用（带重试） ────────────────────────────
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


def call_anthropic_api(config, api_key, messages, body_size_hint: int = 0) -> str:
    url = config["api_base_url"].rstrip("/") + "/v1/messages"
    body = json.dumps({
        "model": config["model"],
        "max_tokens": config.get("max_tokens", 4096),
        "messages": messages,
    }, ensure_ascii=False).encode("utf-8")
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    max_retries = config.get("max_retries", 3)

    def do_request():
        req = urllib_request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib_request.urlopen(req, timeout=calc_timeout(body_size_hint or len(body))) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if "content" in result and len(result["content"]) > 0:
                    # 跳过 thinking 块，取第一个 text 块
                    for block in result["content"]:
                        if block.get("type") == "text" and block.get("text"):
                            return block["text"], False
                    # 兜底：最后一个块的 text
                    last = result["content"][-1]
                    return last.get("text", json.dumps(result, ensure_ascii=False)), False
                return json.dumps(result, ensure_ascii=False), False
        except HTTPError as e:
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
        except URLError as e:
            return f"[网络错误] {e.reason}", True
        except Exception as e:
            return f"[未知错误] {e}", False

    return api_request_with_retry(do_request, max_retries)


def call_openai_api(config, api_key, messages, body_size_hint: int = 0) -> str:
    url = config["api_base_url"].rstrip("/") + "/chat/completions"
    # 转换消息格式（OpenAI 用 image_url）
    converted = []
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

    body = json.dumps({
        "model": config["model"],
        "max_tokens": config.get("max_tokens", 4096),
        "messages": converted,
    }, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "content-type": "application/json",
    }
    max_retries = config.get("max_retries", 3)

    def do_request():
        req = urllib_request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib_request.urlopen(req, timeout=calc_timeout(body_size_hint or len(body))) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if "choices" in result and len(result["choices"]) > 0:
                    return result["choices"][0]["message"]["content"], False
                return json.dumps(result, ensure_ascii=False), False
        except HTTPError as e:
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
        url += "/v1/models"
        body = None
        headers = {"Authorization": f"Bearer {api_key}"}
    req = urllib_request.Request(url, data=body, headers=headers, method="POST" if body else "GET")
    try:
        urllib_request.urlopen(req, timeout=15)
        return True, "配置有效"
    except HTTPError as e:
        err = ""
        try:
            err = e.read().decode("utf-8")[:200]
        except Exception:
            pass
        if e.code == 401:
            return False, f"API Key 无效 (401): {err}"
        if e.code == 400 and "model" in err.lower():
            return False, f"模型不可用 (400): {err}"
        return False, f"HTTP {e.code}: {err}"
    except URLError as e:
        return False, f"网络不可达: {e.reason}"
    except Exception as e:
        return False, f"校验异常: {e}"


# ── 主入口 ────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Vision recognition v3.3")
    parser.add_argument("file_path", nargs="?", help="File path or HTTP URL")
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
    args = parser.parse_args()

    # ── 自动清理过期会话 ──────────────────────────
    config = load_config()
    if "error" not in config:
        ttl = config.get("session_ttl_hours", 24)
        removed = cleanup_expired_sessions(ttl)
        if removed:
            log(f"已清理 {removed} 个过期会话")

    # ── 配置校验模式 ──────────────────────────────
    if args.check:
        config = load_config()
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

    # ── 会话管理命令（不需要 file_path） ──────────
    if args.list_sessions:
        names = list_sessions()
        if not names:
            print("No active sessions")
        else:
            print(f"活跃会话 ({len(names)}):")
            for name in sorted(names):
                try:
                    s = load_session(name)
                    print(f"  {name:20s}  {s.get('file_name','?'):20s}  {s['rounds']}轮  {s['created'][:19]}")
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
        print(export_session(args.session))
        return

    if args.clear and args.session:
        if session_exists(args.session):
            delete_session(args.session)
            print(f"Session '{args.session}' cleared")
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
        log(f"自动会话名: {args.session}")

    # ── 追问模式（有 --ask + --session，但无 file_path）──
    if args.ask and args.session and not args.file_path:
        if not session_exists(args.session):
            print(f"错误: 会话 '{args.session}' 不存在，请先创建: python multimodal.py <文件> --ask '...' --session {args.session}",
                  file=sys.stderr)
            sys.exit(1)

        session = load_session(args.session)
        history = list(session["messages"])

        # 把图片补回第一条 user 消息
        if history and history[0]["role"] == "user":
            image_block = {
                "type": "image",
                "source": {"type": "base64", "media_type": session["media_type"], "data": session["image_b64"]},
            }
            history[0]["content"].insert(0, image_block)

        # 构建消息：历史 + 新问题
        question = args.ask
        history.append({"role": "user", "content": [{"type": "text", "text": question}]})
        messages = history

        config = load_config()
        if "error" in config:
            print(f"错误: {config['error']}", file=sys.stderr)
            sys.exit(1)
        api_key = get_api_key(config)
        provider = config.get("provider", "anthropic").lower()

        log(f"追问: {args.session} (第{session['rounds']+1}轮)")
        log(f"调用: {config.get('model', 'unknown')}")

        if provider in ("anthropic", "mimo"):
            result = call_anthropic_api(config, api_key, messages)
        elif provider in ("openai",):
            result = call_openai_api(config, api_key, messages)
        else:
            result = f"[配置错误] 不支持的 provider: {provider}"

        # 更新会话（保存前去掉图片数据块）
        history.append({"role": "assistant", "content": result})
        save_history = [dict(m) for m in history]
        if save_history and save_history[0]["role"] == "user":
            save_history[0] = {
                "role": "user",
                "content": [c for c in save_history[0]["content"] if c.get("type") != "image"],
            }
        save_session(args.session,
                     image_b64=session["image_b64"],
                     media_type=session["media_type"],
                     file_name=session["file_name"],
                     messages=save_history,
                     config=config)
        safe_print(result)
        return

    # ── 需要 file_path 的命令 ─────────────────────
    if not args.file_path:
        parser.print_help()
        sys.exit(1)

    # ── URL 下载 ──────────────────────────────────
    cleanup_url_file = None
    if is_url(args.file_path):
        try:
            tmp = download_url(args.file_path)
            cleanup_url_file = tmp
            args.file_path = tmp
        except RuntimeError as e:
            print(f"错误: {e}", file=sys.stderr)
            sys.exit(1)

    images_to_process = []  # [(base64, media_type, label)]

    # ── PDF 模式 ────────────────────────────────
    if args.pdf_page:
        if not is_pdf_file(args.file_path):
            print(f"错误: --pdf-page 仅用于 PDF 文件", file=sys.stderr)
            sys.exit(1)
        log(f"PDF 第 {args.pdf_page} 页，渲染中...")
        b64, mime = pdf_page_to_base64(args.file_path, args.pdf_page, dpi=args.dpi)
        images_to_process.append((b64, mime, f"第{args.pdf_page}页"))

    elif args.pdf_range:
        if not is_pdf_file(args.file_path):
            print(f"错误: --pdf-range 仅用于 PDF 文件", file=sys.stderr)
            sys.exit(1)
        parts = args.pdf_range.split("-")
        if len(parts) != 2:
            print(f"错误: --pdf-range 格式应为 起始-结束，如 20-25", file=sys.stderr)
            sys.exit(1)
        start, end = int(parts[0]), int(parts[1])
        log(f"PDF 第 {start}-{end} 页，渲染中...")
        for idx, (b64, mime) in enumerate(pdf_range_to_base64_list(args.file_path, start, end, dpi=args.dpi)):
            images_to_process.append((b64, mime, f"第{start+idx}页"))

    # ── 普通文件模式 ─────────────────────────────
    elif os.path.isfile(args.file_path):
        if is_image_file(args.file_path):
            config = load_config()
            if "error" in config:
                print(f"错误: {config['error']}", file=sys.stderr)
                sys.exit(1)
            if args.no_compress:
                with open(args.file_path, "rb") as f:
                    raw = base64.standard_b64encode(f.read()).decode("utf-8")
                mime, _ = mimetypes.guess_type(args.file_path)
                if not mime:
                    mime = "image/png"
                images_to_process.append((raw, mime, Path(args.file_path).name))
            else:
                image_b64, media_type = encode_image_base64(args.file_path, config)
                images_to_process.append((image_b64, media_type, Path(args.file_path).name))
        else:
            print(f"错误: 不支持的文件格式，请用 --pdf-page 指定页码", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"错误: 文件不存在 — {args.file_path}", file=sys.stderr)
        sys.exit(1)

    # ── 加载配置 ─────────────────────────────────
    config = load_config()
    if "error" in config:
        print(f"错误: {config['error']}", file=sys.stderr)
        sys.exit(1)
    api_key = get_api_key(config)
    if not api_key:
        print(f"错误: 未配置 API Key，请在 {CONFIG_PATH} 中设置 api_key", file=sys.stderr)
        sys.exit(1)

    provider = config.get("provider", "anthropic").lower()
    default_prompt = config.get("prompt", "请详细描述这张图片的内容。")

    # ── 会话冲突检查 ─────────────────────────────
    if args.session and session_exists(args.session) and not args.force:
        print(f"错误: 会话 '{args.session}' 已存在，请用 --force 覆盖或换一个名字", file=sys.stderr)
        sys.exit(1)

    # ── 识别每张图 ───────────────────────────────
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
        session_b64 = image_b64  # 用于保存会话
        session_mime = media_type

        if args.session and session_exists(args.session):
            # 追加到已有会话
            session = load_session(args.session)
            history = session["messages"]
            session_b64 = session["image_b64"]
            session_mime = session["media_type"]

        is_first_in_session = args.session and not history
        image_for_api = session_b64 if history else image_b64

        messages = build_messages(image_for_api, session_mime, question, history)

        log(f"调用: {config.get('model', 'unknown')}")

        if provider in ("anthropic", "mimo"):
            result = call_anthropic_api(config, api_key, messages)
        elif provider in ("openai",):
            result = call_openai_api(config, api_key, messages)
        else:
            result = f"[配置错误] 不支持的 provider: {provider}"

        # 保存会话
        if args.session:
            history = list(history)
            history.append({"role": "user", "content": [{"type": "text", "text": question}]})
            history.append({"role": "assistant", "content": result})
            save_session(args.session,
                         image_b64=session_b64,
                         media_type=session_mime,
                         file_name=Path(args.file_path).name,
                         messages=history,
                         config=config)
            log(f"会话已保存: {args.session}")

        if len(images_to_process) > 1:
            print(f"\n===== {label} =====")
        safe_print(result)

    # ── URL 临时文件清理 ────────────────────────
    if cleanup_url_file:
        try:
            os.unlink(cleanup_url_file)
        except Exception:
            pass


if __name__ == "__main__":
    main()
