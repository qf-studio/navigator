#!/usr/bin/env python3
"""
Source notes for nav-deep-research (TASK-74).

Every fetched page becomes ``.agent/research/<slug>/sources/NNN.md``: a small
frontmatter block (id, url, final_url, canonical_url, title, fetched_at,
suggested_by, fetch_method, http_status, status, reason, chars, truncated,
sha256) followed by the body wrapped in the ``<nav-untrusted-source>`` fence.

Commands (all print JSON except ``digest``):
  fetch   --url U --run SLUG [--lens breadth|canonical|adversarial|gap]
          [--max-chars N] [--timeout S]
  write   --url U --run SLUG --body-file F --fetch-method webfetch [--title T]
  list    --run SLUG [--status ok]
  digest  --run SLUG [--head-chars N]      per-source digest for the writer (markdown)
  refetch --run SLUG                       rebuild bodies of notes whose file is missing

Fetch policy (stdlib urllib, no cookies, no JS):
- canonical URL: lowercase scheme/host, no fragment, no utm_*/fbclid/gclid,
  no trailing slash; dedup on canonical(url) and canonical(final_url) within a run
- a ``blocked``/``skipped`` stub never wins over a later ``ok`` write for the same
  URL: the ok note replaces the stub under the stub's id (``superseded: true``), so
  a WebFetch fallback after a blocked raw fetch yields exactly one ok note (GH-34)
- Content-Type outside text/html|text/plain|application/xhtml → status skipped
- 401/403/429/503, network failure, or a thin body carrying bot-wall markers →
  status blocked (the fetcher may then fall back to WebFetch and use ``write``)
- read cap 2 MB, body clamp ``--max-chars`` (default 40k) with ``truncated: true``
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from untrusted import unwrap_body, wrap_body  # noqa: E402

USER_AGENT = "Mozilla/5.0 (compatible; navigator-deep-research/1.0; +https://navigator.dev)"
READ_CAP_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_CHARS = 40_000
DEFAULT_TIMEOUT = 20
TEXT_TYPES = ("text/html", "text/plain", "application/xhtml+xml")
BLOCKED_STATUSES = {401, 403, 429, 503}
BLOCKED_MARKERS = ("captcha", "enable javascript", "access denied", "verify you are human",
                   "are you a robot", "cloudflare", "please log in", "sign in to continue")
THIN_BODY_CHARS = 400
_TRACKING = re.compile(r"^(utm_\w+|fbclid|gclid|mc_cid|mc_eid|ref|igshid)$", re.IGNORECASE)
_SKIP_TAGS = {"script", "style", "noscript", "template", "nav", "header", "footer", "aside",
              "svg", "iframe"}
_BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "table", "tr", "section", "article",
               "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "hr", "dd", "dt"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sources_dir(slug: str, agent_dir: str = ".agent") -> Path:
    return Path(agent_dir) / "research" / slug / "sources"


# --------------------------------------------------------------------------- URLs
def canonical_url(url: str) -> str:
    parts = urllib.parse.urlsplit((url or "").strip())
    scheme = parts.scheme.lower()
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
             if not _TRACKING.match(k)]
    path = re.sub(r"/+$", "", parts.path) or ""
    return urllib.parse.urlunsplit((scheme, host, path, urllib.parse.urlencode(query), ""))


# --------------------------------------------------------------------------- HTML
class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._chunks: list[str] = []
        self._in_title = False
        self.title = ""
        self.headings: list[str] = []
        self._heading: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = True
        if tag in ("h1", "h2"):
            self._heading = []
        if tag in _BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = False
        if tag in ("h1", "h2") and self._heading is not None:
            text = " ".join("".join(self._heading).split())
            if text:
                self.headings.append(text)
            self._heading = None
        if tag in _BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._in_title:
            self.title += data
        if self._heading is not None:
            self._heading.append(data)
        self._chunks.append(data)

    def text(self) -> str:
        raw = "".join(self._chunks)
        lines = [" ".join(line.split()) for line in raw.splitlines()]
        out, blank = [], 0
        for line in lines:
            if line:
                out.append(line)
                blank = 0
            else:
                blank += 1
                if blank == 1:
                    out.append("")
        return "\n".join(out).strip()


def extract_text(html_text: str) -> tuple[str, str, list[str]]:
    """(body text, title, h1/h2 headings) from HTML."""
    parser = _TextExtractor()
    parser.feed(html_text or "")
    parser.close()
    return parser.text(), " ".join(parser.title.split()), parser.headings


# --------------------------------------------------------------------------- fetch
def fetch_url(url: str, timeout: int = DEFAULT_TIMEOUT, opener=None) -> dict:
    """Raw HTTP fetch. Returns {ok, status_code, final_url, content_type, text, error}."""
    opener = opener or urllib.request.build_opener()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                   "Accept": "text/html,text/plain;q=0.9,*/*;q=0.5"})
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(READ_CAP_BYTES)
            headers = response.headers
            content_type = (headers.get_content_type() or "").lower()
            charset = headers.get_content_charset() or "utf-8"
            status_code = getattr(response, "status", 200) or 200
            final_url = response.geturl() or url
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status_code": exc.code, "final_url": url, "content_type": "",
                "text": "", "error": f"http {exc.code}"}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return {"ok": False, "status_code": 0, "final_url": url, "content_type": "",
                "text": "", "error": f"network: {exc}"[:200]}
    try:
        text = raw.decode(charset, errors="replace")
    except LookupError:
        text = raw.decode("utf-8", errors="replace")
    return {"ok": True, "status_code": status_code, "final_url": final_url,
            "content_type": content_type, "text": text, "error": ""}


def classify(fetched: dict, body_text: str) -> tuple[str, str]:
    """(status, reason) for a fetch result + extracted body."""
    code = fetched.get("status_code", 0)
    if not fetched.get("ok"):
        if code in BLOCKED_STATUSES or code == 0:
            return "blocked", fetched.get("error") or f"http {code}"
        return "skipped", fetched.get("error") or f"http {code}"
    ctype = fetched.get("content_type", "")
    if ctype and not any(ctype.startswith(t) for t in TEXT_TYPES):
        return "skipped", f"non-text content-type: {ctype}"
    lowered = body_text.lower()
    if len(body_text) < THIN_BODY_CHARS and any(m in lowered for m in BLOCKED_MARKERS):
        return "blocked", "thin body with bot-wall markers"
    if not body_text.strip():
        return "skipped", "empty body"
    return "ok", ""


# --------------------------------------------------------------------------- notes
def _fm_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = "" if value is None else str(value)
    if text == "" or any(ch in text for ch in ":#\"'\n") or text != text.strip():
        return json.dumps(text, ensure_ascii=False)
    return text


def _parse_value(raw: str):
    raw = raw.strip()
    if raw in ("true", "false"):
        return raw == "true"
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if raw.startswith('"'):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    return raw


def render_note(meta: dict, body: str) -> str:
    order = ["id", "url", "final_url", "canonical_url", "title", "fetched_at", "suggested_by",
             "fetch_method", "http_status", "status", "reason", "chars", "truncated", "sha256",
             "headings"]
    lines = ["---"]
    for key in order:
        if key in meta:
            lines.append(f"{key}: {_fm_value(meta[key])}")
    for key, value in meta.items():
        if key not in order:
            lines.append(f"{key}: {_fm_value(value)}")
    lines.append("---")
    lines.append("")
    lines.append(wrap_body(body, meta.get("url", "")) if body else "")
    return "\n".join(lines).rstrip("\n") + "\n"


def parse_note(text: str) -> tuple[dict, str]:
    """(frontmatter dict, inner body without the fence)."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    meta: dict = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        meta[key] = value.strip() if key == "id" else _parse_value(value)
    body = text[end + 5:].lstrip("\n")
    return meta, unwrap_body(body)


def load_notes(slug: str, agent_dir: str = ".agent") -> list[tuple[dict, str, Path]]:
    directory = sources_dir(slug, agent_dir)
    notes = []
    if not directory.is_dir():
        return notes
    for path in sorted(directory.glob("*.md")):
        meta, body = parse_note(path.read_text(encoding="utf-8", errors="replace"))
        if meta.get("id"):
            notes.append((meta, body, path))
    return notes


def next_id(slug: str, agent_dir: str = ".agent") -> str:
    directory = sources_dir(slug, agent_dir)
    existing = [int(p.stem) for p in directory.glob("*.md") if p.stem.isdigit()] \
        if directory.is_dir() else []
    return f"{(max(existing) + 1) if existing else 1:03d}"


def find_duplicate(slug: str, url: str, agent_dir: str = ".agent") -> dict | None:
    wanted = canonical_url(url)
    for meta, _, _ in load_notes(slug, agent_dir):
        if wanted in (meta.get("canonical_url"), canonical_url(str(meta.get("final_url", "")))):
            return meta
    return None


def _dedup_result(duplicate: dict, slug: str, agent_dir: str) -> dict:
    return {"id": duplicate["id"], "status": duplicate.get("status"), "deduped": True,
            "path": str(sources_dir(slug, agent_dir) / f"{duplicate['id']}.md")}


def _is_stub(meta: dict | None) -> bool:
    """A note that carries no body (blocked or skipped) and may be superseded."""
    return bool(meta) and meta.get("status") in ("blocked", "skipped")


# Which search lens produced a URL (TASK-78). Recorded in ``suggested_by`` so the
# writer, the critic and the gate can tell a canonical source from a breadth one.
# ``canonical`` = primary/authoritative (spec, vendor doc, paper, issue tracker).
LENSES = ("breadth", "canonical", "adversarial", "gap")
DEFAULT_LENS = "unspecified"


def normalize_lens(value) -> str:
    """A lens name from ``LENSES``, or ``unspecified`` for anything else.

    Pre-TASK-78 runs wrote ``seed``; unknown values degrade the same way rather
    than failing a fetch, because a mislabelled source is better than a lost one.
    """
    name = str(value or "").strip().lower()
    return name if name in LENSES else DEFAULT_LENS


def store_note(slug: str, url: str, body: str, *, title: str = "", final_url: str = "",
               fetch_method: str = "raw", http_status: int = 0, status: str = "ok",
               reason: str = "", suggested_by: str = "seed", headings: list[str] | None = None,
               max_chars: int = DEFAULT_MAX_CHARS, agent_dir: str = ".agent") -> dict:
    directory = sources_dir(slug, agent_dir)
    if not directory.parent.exists():
        raise FileNotFoundError(f"run {slug!r} not found under {directory.parent.parent}")
    directory.mkdir(parents=True, exist_ok=True)
    duplicate = find_duplicate(slug, url, agent_dir)
    supersede = _is_stub(duplicate) and status == "ok"
    if duplicate and not supersede:
        return _dedup_result(duplicate, slug, agent_dir)
    truncated = len(body) > max_chars
    body = body[:max_chars] if truncated else body
    if supersede:
        # The existing note is a bodiless stub (blocked/skipped) and this write is
        # ok — e.g. the WebFetch fallback after a blocked raw fetch. Reuse its id so
        # the URL has exactly one note and no dangling reference (GH-34).
        note_id = duplicate["id"]
        handle = open(directory / f"{note_id}.md", "w", encoding="utf-8")
    else:
        # Parallel fetchers write concurrently: claim the id with an exclusive create
        # and retry on collision instead of trusting a precomputed next_id.
        for _ in range(1000):
            note_id = next_id(slug, agent_dir)
            try:
                handle = open(directory / f"{note_id}.md", "x", encoding="utf-8")
            except FileExistsError:
                continue
            break
        else:  # pragma: no cover - only if a thousand ids collide
            raise RuntimeError("could not allocate a source id")
    meta = {
        "id": note_id,
        "url": url,
        "final_url": final_url or url,
        "canonical_url": canonical_url(url),
        "title": title or url,
        "fetched_at": now_iso(),
        "suggested_by": normalize_lens(suggested_by),
        "fetch_method": fetch_method,
        "http_status": http_status,
        "status": status,
        "reason": reason,
        "chars": len(body),
        "truncated": truncated,
        "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest() if body else "",
        "headings": " | ".join(headings[:12]) if headings else "",
    }
    path = directory / f"{note_id}.md"
    with handle:
        handle.write(render_note(meta, body if status == "ok" else ""))
    return {"id": note_id, "status": status, "reason": reason, "deduped": False,
            "superseded": supersede, "path": str(path), "chars": len(body),
            "truncated": truncated, "title": meta["title"]}


def fetch_and_store(slug: str, url: str, *, suggested_by: str = "seed",
                    max_chars: int = DEFAULT_MAX_CHARS, timeout: int = DEFAULT_TIMEOUT,
                    agent_dir: str = ".agent", opener=None) -> dict:
    duplicate = find_duplicate(slug, url, agent_dir)
    if duplicate and not _is_stub(duplicate):
        return _dedup_result(duplicate, slug, agent_dir)
    # A stub (blocked/skipped) does not block a retry: refetch, and let store_note
    # supersede the stub if this attempt comes back ok.
    fetched = fetch_url(url, timeout=timeout, opener=opener)
    body, title, headings = "", "", []
    if fetched["ok"]:
        if fetched["content_type"].startswith("text/plain"):
            body = fetched["text"]
        else:
            body, title, headings = extract_text(fetched["text"])
    status, reason = classify(fetched, body)
    return store_note(slug, url, body, title=title, final_url=fetched["final_url"],
                      fetch_method="raw", http_status=fetched["status_code"], status=status,
                      reason=reason, suggested_by=suggested_by, headings=headings,
                      max_chars=max_chars, agent_dir=agent_dir)


def digest(slug: str, head_chars: int = 1500, agent_dir: str = ".agent") -> str:
    """Markdown digest of every ok source: frontmatter + headings + fenced head."""
    parts = []
    for meta, body, _ in load_notes(slug, agent_dir):
        if meta.get("status") != "ok":
            continue
        head = body[:head_chars]
        parts.append(
            f"### [{meta['id']}] {meta.get('title', '')}\n"
            f"url: {meta.get('url', '')}\n"
            f"lens: {meta.get('suggested_by', DEFAULT_LENS)}\n"
            f"fetch_method: {meta.get('fetch_method', 'raw')} | chars: {meta.get('chars', 0)}"
            f" | truncated: {str(meta.get('truncated', False)).lower()}\n"
            f"headings: {meta.get('headings', '') or '-'}\n\n"
            f"{wrap_body(head, str(meta.get('url', '')))}\n"
        )
    return "\n".join(parts)


def refetch(slug: str, agent_dir: str = ".agent", opener=None,
            timeout: int = DEFAULT_TIMEOUT) -> list[dict]:
    """Rebuild bodies of raw notes whose body is missing (e.g. sources/ was gitignored)."""
    results = []
    for meta, body, path in load_notes(slug, agent_dir):
        if meta.get("status") != "ok" or body.strip() or meta.get("fetch_method") != "raw":
            continue
        fetched = fetch_url(str(meta["url"]), timeout=timeout, opener=opener)
        if not fetched["ok"]:
            results.append({"id": meta["id"], "ok": False, "error": fetched["error"]})
            continue
        new_body, _, _ = extract_text(fetched["text"])
        new_body = new_body[: int(meta.get("chars") or DEFAULT_MAX_CHARS)]
        meta["sha256_refetched"] = hashlib.sha256(new_body.encode("utf-8")).hexdigest()
        meta["refetched_at"] = now_iso()
        path.write_text(render_note(meta, new_body), encoding="utf-8")
        results.append({"id": meta["id"], "ok": True,
                        "sha_match": meta["sha256_refetched"] == meta.get("sha256")})
    return results


# --------------------------------------------------------------------------- CLI
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="nav-deep-research source notes")
    parser.add_argument("--agent-dir", default=".agent")
    sub = parser.add_subparsers(dest="command", required=True)

    p_fetch = sub.add_parser("fetch")
    p_fetch.add_argument("--url", required=True)
    p_fetch.add_argument("--run", required=True)
    p_fetch.add_argument("--lens", "--suggested-by", dest="suggested_by",
                         default=DEFAULT_LENS, help="search lens that produced the URL")
    p_fetch.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    p_fetch.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)

    p_write = sub.add_parser("write")
    p_write.add_argument("--url", required=True)
    p_write.add_argument("--run", required=True)
    p_write.add_argument("--body-file", required=True)
    p_write.add_argument("--fetch-method", default="webfetch")
    p_write.add_argument("--title", default="")
    p_write.add_argument("--lens", "--suggested-by", dest="suggested_by",
                         default=DEFAULT_LENS, help="search lens that produced the URL")
    p_write.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)

    p_list = sub.add_parser("list")
    p_list.add_argument("--run", required=True)
    p_list.add_argument("--status")

    p_digest = sub.add_parser("digest")
    p_digest.add_argument("--run", required=True)
    p_digest.add_argument("--head-chars", type=int, default=1500)

    p_refetch = sub.add_parser("refetch")
    p_refetch.add_argument("--run", required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "fetch":
            out = fetch_and_store(args.run, args.url, suggested_by=args.suggested_by,
                                  max_chars=args.max_chars, timeout=args.timeout,
                                  agent_dir=args.agent_dir)
        elif args.command == "write":
            body = Path(args.body_file).read_text(encoding="utf-8", errors="replace")
            out = store_note(args.run, args.url, body, title=args.title,
                             fetch_method=args.fetch_method, http_status=200,
                             suggested_by=args.suggested_by, max_chars=args.max_chars,
                             agent_dir=args.agent_dir)
        elif args.command == "list":
            out = [meta for meta, _, _ in load_notes(args.run, args.agent_dir)
                   if not args.status or meta.get("status") == args.status]
        elif args.command == "digest":
            print(digest(args.run, args.head_chars, args.agent_dir))
            return 0
        else:
            out = refetch(args.run, args.agent_dir)
    except (FileNotFoundError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 1
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
