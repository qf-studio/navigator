#!/usr/bin/env python3
"""
Navigator CLAUDE.md Updater
Extracts customizations and generates updated CLAUDE.md with v3.1 template
"""

import sys
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib import request
from urllib.error import URLError, HTTPError

# ---------------------------------------------------------------------------
# v7 hook-liveness sequencing guard (TASK-63 Phase 5, mem-036 class)
#
# The v7 CLAUDE.md template demotes prose mandates in favor of hook-runtime
# enforcement. Regenerating CLAUDE.md while the hook runtime is dead would
# leave a project with NEITHER prose NOR enforcement, so regeneration is
# gated on OBSERVED dispatcher liveness — never on manifest or config
# inspection, which both look fine while hooks are silently no-op (exactly
# how mem-036 shipped broken for two releases).
#
# Liveness proof — EITHER file suffices:
#   - fresh runtime state .agent/.nav-runtime-state.json
#     (meta.schema == 2 and meta.updated within LIVENESS_MAX_AGE_DAYS), or
#   - fresh dispatch health .agent/.nav-dispatch-health.json
#     (last_error.ts within LIVENESS_MAX_AGE_DAYS).
# The dispatcher writes the health file on ERROR only, so its absence is
# normal on a healthy install — the state file is the primary signal; a
# fresh error record still proves the dispatcher ran.
# ---------------------------------------------------------------------------
LIVENESS_MAX_AGE_DAYS = 7
RUNTIME_STATE_RELPATH = ".agent/.nav-runtime-state.json"
DISPATCH_HEALTH_RELPATH = ".agent/.nav-dispatch-health.json"
RUNTIME_STATE_SCHEMA = 2


def _parse_iso_timestamp(value) -> Optional[float]:
    """ISO 8601 string -> epoch seconds; None on anything unparseable."""
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _read_json_object(path: Path) -> Optional[Dict]:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _is_fresh(ts: Optional[float], now_ts: float) -> bool:
    if ts is None:
        return False
    return (now_ts - ts) <= LIVENESS_MAX_AGE_DAYS * 86400


def _state_file_is_fresh(path: Path, now_ts: float) -> bool:
    """Fresh .nav-runtime-state.json: meta.schema == 2, meta.updated in window."""
    doc = _read_json_object(path)
    if doc is None:
        return False
    meta = doc.get("meta")
    if not isinstance(meta, dict) or meta.get("schema") != RUNTIME_STATE_SCHEMA:
        return False
    return _is_fresh(_parse_iso_timestamp(meta.get("updated")), now_ts)


def _health_file_is_fresh(path: Path, now_ts: float) -> bool:
    """Fresh .nav-dispatch-health.json: last_error.ts in window."""
    doc = _read_json_object(path)
    if doc is None:
        return False
    last = doc.get("last_error")
    if not isinstance(last, dict):
        return False
    return _is_fresh(_parse_iso_timestamp(last.get("ts")), now_ts)


def check_hook_liveness(project_root, now: Optional[float] = None) -> Tuple[bool, str]:
    """(True, "") when the hook runtime is provably live; else (False, message).

    `project_root` is the directory that holds `.agent/` — for regeneration
    that is the parent of the target CLAUDE.md. `now` is injectable epoch
    seconds for tests.
    """
    root = Path(project_root)
    now_ts = datetime.now(tz=timezone.utc).timestamp() if now is None else float(now)
    state_path = root / RUNTIME_STATE_RELPATH
    health_path = root / DISPATCH_HEALTH_RELPATH

    if _state_file_is_fresh(state_path, now_ts):
        return True, ""
    if _health_file_is_fresh(health_path, now_ts):
        return True, ""

    message = "\n".join([
        "Hook-liveness sequencing guard: refusing CLAUDE.md regeneration.",
        "",
        "No proof that the Navigator hook runtime is live in this project. Checked:",
        f"  - {state_path}",
        f"    (need meta.schema == {RUNTIME_STATE_SCHEMA} and meta.updated within "
        f"{LIVENESS_MAX_AGE_DAYS} days)",
        f"  - {health_path}",
        f"    (need last_error.ts within {LIVENESS_MAX_AGE_DAYS} days)",
        "",
        "Both are absent or stale. Regenerating the demoted CLAUDE.md now would leave",
        "this project with neither prose mandates nor hook enforcement (mem-036 class).",
        "The existing CLAUDE.md was left untouched.",
        "",
        "Remedy: start a Claude Code session in this project so the dispatcher stamps",
        f"{RUNTIME_STATE_RELPATH}, then re-run the sync.",
    ])
    return False, message

def get_plugin_version() -> Optional[str]:
    """
    Get installed Navigator plugin version from plugin.json.

    Returns:
        Version string (e.g., "4.3.0") or None if not found
    """
    # Check multiple possible installation paths
    possible_paths = [
        # Legacy marketplace paths
        Path.home() / '.claude' / 'plugins' / 'marketplaces' / 'navigator-marketplace' / '.claude-plugin' / 'plugin.json',
        Path.home() / '.config' / 'claude' / 'plugins' / 'navigator' / '.claude-plugin' / 'plugin.json',
        Path.home() / '.claude' / 'plugins' / 'navigator' / '.claude-plugin' / 'plugin.json',
    ]

    # For the cache path, need to find versioned subdirectory
    cache_base = Path.home() / '.claude' / 'plugins' / 'cache' / 'navigator-marketplace' / 'navigator'
    if cache_base.exists():
        # Find the latest version directory
        version_dirs = sorted([d for d in cache_base.iterdir() if d.is_dir()], reverse=True)
        if version_dirs:
            plugin_json = version_dirs[0] / '.claude-plugin' / 'plugin.json'
            if plugin_json.exists():
                try:
                    with open(plugin_json, 'r') as f:
                        data = json.load(f)
                        return data.get('version')
                except (json.JSONDecodeError, OSError):
                    pass

    for path in possible_paths:
        if path.is_file():
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    return data.get('version')
            except (json.JSONDecodeError, OSError):
                continue

    return None


def installed_plugin_version() -> Optional[str]:
    """Version of the plugin this script ships with, else the installed one.

    The skill layout (`skills/<skill>/functions/<script>`) is the same in the
    source repo and in the marketplace cache, so the nearest ancestor holding
    `.claude-plugin/plugin.json` is the plugin that runs this sync. The
    home-directory lookup in `get_plugin_version` is the fallback.
    """
    for parent in Path(__file__).resolve().parents:
        manifest = parent / '.claude-plugin' / 'plugin.json'
        if manifest.is_file():
            data = _read_json_object(manifest)
            version = data.get('version') if data else None
            if isinstance(version, str) and version:
                return version
    return get_plugin_version()


def fetch_template_from_github(version: Optional[str] = None) -> Optional[str]:
    """
    Fetch CLAUDE.md template from GitHub releases.

    Priority:
    1. Specified version (e.g., 'v4.3.0' or '4.3.0')
    2. Detected plugin version
    3. Returns None (caller should use bundled fallback)

    Args:
        version: Specific version to fetch (optional)

    Returns:
        Template content as string, or None if fetch fails
    """
    if not version:
        version = get_plugin_version()

    if not version:
        return None

    # Ensure version has 'v' prefix for GitHub URL
    if not version.startswith('v'):
        version = f'v{version}'

    github_url = f"https://raw.githubusercontent.com/qf-studio/navigator/{version}/templates/CLAUDE.md"

    try:
        req = request.Request(github_url)
        req.add_header('User-Agent', 'Navigator-CLAUDE-Updater')

        with request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                content = response.read().decode('utf-8')
                return content
    except (URLError, HTTPError, TimeoutError) as e:
        # Silent fail - caller will use bundled template
        print(f"⚠️  Could not fetch template from GitHub ({version}): {e}", file=sys.stderr)
        print(f"   Falling back to bundled template", file=sys.stderr)
        return None

    return None

def get_template_path(bundled_template_dir: str, version: Optional[str] = None) -> tuple[str, bool]:
    """
    Get template path, preferring GitHub source over bundled.

    Args:
        bundled_template_dir: Path to bundled templates directory
        version: Optional specific version to fetch

    Returns:
        Tuple of (template_path_or_content, is_from_github)
    """
    # Try GitHub first
    github_template = fetch_template_from_github(version)

    if github_template:
        # Write to temporary file
        import tempfile
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False)
        temp_file.write(github_template)
        temp_file.close()

        detected_version = version or get_plugin_version()
        print(f"✓ Using template from GitHub ({detected_version})", file=sys.stderr)
        return (temp_file.name, True)

    # Fallback to bundled
    bundled_path = Path(bundled_template_dir) / 'CLAUDE.md'
    if bundled_path.exists():
        bundled_version = get_plugin_version() or "unknown"
        print(f"✓ Using bundled template (v{bundled_version})", file=sys.stderr)
        return (str(bundled_path), False)

    raise FileNotFoundError(f"No template found (GitHub failed, bundled not at {bundled_path})")


# ---------------------------------------------------------------------------
# Extract / generate
#
# Model: the project's CLAUDE.md is the truth for everything the template
# leaves to the project. `extract` records the file's layout verbatim: the
# title, the preamble, and every `##` section in order, with fenced code
# blocks kept whole (a `# comment` inside a bash block is not a header).
# `generate` renders that layout back and replaces only the text Navigator
# owns: the `## Navigator` body or the `**Navigator runtime**` paragraph
# wherever the project keeps it, plus the two stamp lines (**Last Updated**,
# **Navigator Version**). Template sections the project lacks are added;
# nothing the project wrote is dropped, renamed or re-ordered. A round trip on
# an already-current file therefore changes only the two stamp lines.
#
# The flat lists (`code_standards`, `forbidden_actions`, `custom_sections`,
# `custom_section_anchors`) stay in the JSON for readers of the extract output
# and for hand-written customizations without a `sections` layout, which
# `generate` renders through the template as before (TASK-105).
# ---------------------------------------------------------------------------

VIOLATIONS_MARKER = "[Add project-specific violations here]"
STANDARDS_PLACEHOLDER = "[Customize for your project's framework and patterns]"
DESCRIPTION_PLACEHOLDER = "[Brief project description - explain what this project does]"
TECH_STACK_PLACEHOLDER = "[List your technologies, e.g., Next.js, TypeScript, PostgreSQL]"
RUNTIME_PARAGRAPH_PREFIX = "**Navigator runtime"
STAMP_FIELDS = ("Last Updated", "Navigator Version")

# Sections whose content `generate` renders itself from the flat lists (the
# legacy path). Any other `##` header is a custom section in that path. "Code
# Standards" is the pre-v7 name of the standards section.
STANDARD_SECTIONS = [
    "Context", "Navigator", "Code Standards",
    "Project-Specific Code Standards", "Forbidden Actions",
]

# A project that keeps a template section under an older name has that
# section; the layout path adds no second copy under the template's name.
SECTION_ALIASES = {"Project-Specific Code Standards": ("Code Standards",)}

_FENCE_RE = re.compile(r'^\s{0,3}(`{3,}|~{3,})')
_HEADER_LINE_RE = re.compile(r'^(#{1,2})\s+(.*?)\s*$')


def _scan_headers(content: str) -> List[Tuple[int, str, int, int]]:
    """`(level, title, line_start, line_end)` for every `#`/`##` header line
    outside fenced code blocks. `line_end` is the offset just past the line's
    newline (or the end of the text)."""
    headers = []
    fence = None
    offset = 0
    for line in content.splitlines(keepends=True):
        bare = line.rstrip('\r\n')
        fence_match = _FENCE_RE.match(bare)
        if fence is None and fence_match:
            fence = fence_match.group(1)[0]
        elif fence is not None and fence_match and fence_match.group(1)[0] == fence \
                and not bare.strip()[len(fence_match.group(1)):].strip():
            fence = None
        elif fence is None:
            match = _HEADER_LINE_RE.match(bare)
            if match:
                headers.append((len(match.group(1)), match.group(2),
                                offset, offset + len(line)))
        offset += len(line)
    return headers


def _trim_blank_lines(text: str) -> str:
    """Drop leading and trailing blank lines; keep every other byte."""
    lines = text.split('\n')
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return '\n'.join(lines)


def _section_bodies(content: str) -> List[Tuple[int, str, str]]:
    """`(level, title, body)` for every header; a body runs to the next header."""
    headers = _scan_headers(content)
    bodies = []
    for index, (level, title, _start, end) in enumerate(headers):
        next_start = headers[index + 1][2] if index + 1 < len(headers) else len(content)
        bodies.append((level, title, _trim_blank_lines(content[end:next_start])))
    return bodies


def _header_match(content: str, header: str) -> Optional[re.Match]:
    """Match a `#`/`##` header line that starts with `header`."""
    pattern = r'^#{1,2}\s+' + re.escape(header) + r'.*?$'
    return re.search(pattern, content, re.MULTILINE | re.IGNORECASE)


def extract_section(content: str, header: str,
                    next_headers: Optional[List[str]] = None) -> Optional[str]:
    """Body of the first `#`/`##` section titled `header` (case-insensitive),
    up to the next `#`/`##` header outside fenced code blocks.

    `next_headers` is accepted for backward compatibility and ignored: a
    section ends at the next top-level header whatever its name, so an
    unknown custom section is never swallowed into the one before it.
    """
    wanted = header.strip().lower()
    for _level, title, body in _section_bodies(content):
        if title.lower() == wanted:
            return body if body.strip() else None
    return None


def _is_bullet(stripped: str) -> bool:
    return len(stripped) > 1 and stripped[0] in '-*' and stripped[1] == ' '


def _list_items(section: str) -> List[Tuple[str, str]]:
    """Split a section body into ('bullet', text) and ('loose', text) items.

    A bullet keeps its continuation lines (indented lines that follow it)
    with their original indentation, joined by newlines, so it renders back
    byte for byte. Headers and bold field lines are skipped. Any other
    unindented line is 'loose'.
    """
    items: List[Tuple[str, str]] = []
    for raw in section.split('\n'):
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith('#') or stripped.startswith('**'):
            continue
        if _is_bullet(stripped):
            text = stripped[1:].strip()
            if text:
                items.append(('bullet', text))
        elif raw[:1].isspace() and items and items[-1][0] == 'bullet':
            kind, text = items[-1]
            items[-1] = (kind, text + '\n' + raw.rstrip())
        else:
            items.append(('loose', stripped))
    return items


def _field_value(context: str, field: str) -> str:
    """Value of a `**Field**: ...` line plus its continuation lines.

    The value ends at a blank line or at the next `**` field line. A
    placeholder value (starts with `[`) counts as empty.
    """
    lines = context.split('\n')
    prefix = f'**{field}**:'
    for index, line in enumerate(lines):
        if not line.startswith(prefix):
            continue
        parts = [line[len(prefix):].strip()]
        for continuation in lines[index + 1:]:
            if not continuation.strip() or continuation.startswith('**'):
                break
            parts.append(continuation.rstrip())
        value = '\n'.join(parts).strip()
        return '' if value.startswith('[') else value
    return ''


def _runtime_paragraph_span(body: str) -> Optional[Tuple[int, int]]:
    """Offsets of the `**Navigator runtime...**:` paragraph inside `body`
    (from its first line up to the next blank line), or None."""
    match = re.search(r'^' + re.escape(RUNTIME_PARAGRAPH_PREFIX) + r'.*?\*\*:',
                      body, re.MULTILINE)
    if not match:
        return None
    end = body.find('\n\n', match.start())
    return match.start(), (len(body) if end == -1 else end)


def _navigator_section_title(sections: List[Dict[str, str]]) -> str:
    """Title of the section Navigator owns: `## Navigator` when present, else
    the first section whose body carries the runtime paragraph; '' if none."""
    for section in sections:
        if section["header"].lower() == "navigator":
            return section["header"]
    for section in sections:
        if _runtime_paragraph_span(section["body"]) is not None:
            return section["header"]
    return ""


def extract_customizations(claude_md_path: str) -> Dict:
    """Extract project-specific customizations from CLAUDE.md"""

    source = Path(claude_md_path).resolve()
    with open(source, 'r', encoding='utf-8') as f:
        content = f.read()

    customizations: Dict = {
        "project_name": "",
        "title": "",
        "description": "",
        "tech_stack": [],
        "core_principle": "",
        "code_standards": [],
        "forbidden_actions": [],
        "violations_marker": False,
        "pm_tool": "none",
        "custom_sections": {},
        "custom_section_anchors": {},
        "has_context": False,
        "preamble": "",
        "sections": [],
        "navigator_section": "",
        "source_dir": str(source.parent),
    }

    # Title: the first `#` header, verbatim. The project name is the part
    # before " - Claude Code Configuration" when the title has that shape
    # (the dash needs whitespace on both sides so a hyphenated project name
    # survives), else the whole title.
    headers = _scan_headers(content)
    h1 = next((h for h in headers if h[0] == 1), None)
    if h1:
        customizations["title"] = h1[1]
        title_match = re.match(r'^(.+?)\s+-\s+Claude Code Configuration$', h1[1])
        customizations["project_name"] = (
            title_match.group(1).strip() if title_match else h1[1])

    # Layout: the preamble (between the title and the first `##`) and every
    # `##` section in order, bodies verbatim.
    level2 = [h for h in headers if h[0] == 2]
    preamble_start = h1[3] if h1 else 0
    preamble_end = level2[0][2] if level2 else len(content)
    customizations["preamble"] = _trim_blank_lines(content[preamble_start:preamble_end])
    customizations["sections"] = [
        {"header": title, "body": body}
        for level, title, body in _section_bodies(content) if level == 2
    ]
    customizations["navigator_section"] = _navigator_section_title(
        customizations["sections"])

    # Context: description (every line before the first `**` field, minus
    # placeholders, line breaks kept), tech stack, core principle.
    context = extract_section(content, "Context")
    customizations["has_context"] = context is not None
    if context:
        desc_lines = []
        for line in context.split('\n'):
            if line.startswith('**'):
                break
            if line.strip().startswith('['):
                continue
            desc_lines.append(line.rstrip())
        customizations["description"] = '\n'.join(desc_lines).strip()

        tech_match = re.search(r'\*\*Tech Stack\*\*:\s*(.+?)(?:\n|$)', context)
        if tech_match:
            tech_text = re.sub(r'\[|\]', '', tech_match.group(1).strip())
            if tech_text:
                customizations["tech_stack"] = [t.strip() for t in tech_text.split(',')]

        customizations["core_principle"] = _field_value(context, "Core Principle")

    # Code standards: every bullet the project lists, verbatim and in order.
    # Template defaults the project kept stay; defaults it removed stay gone.
    standards_section = (extract_section(content, "Project-Specific Code Standards")
                         or extract_section(content, "Code Standards"))
    if standards_section:
        for kind, text in _list_items(standards_section):
            if kind == 'bullet':
                customizations["code_standards"].append(text)
            elif ':' in text and not text.startswith('['):
                # Legacy shape: "Custom rule: Always use hooks" without a dash.
                customizations["code_standards"].append(text)

    # Forbidden actions: every bullet, the ❌ prefix normalized away.
    forbidden_section = extract_section(content, "Forbidden Actions")
    if forbidden_section:
        customizations["violations_marker"] = VIOLATIONS_MARKER in forbidden_section
        for kind, text in _list_items(forbidden_section):
            if kind == 'loose' and not text.startswith('❌'):
                continue
            action = text.lstrip('❌ ').strip()
            if action:
                customizations["forbidden_actions"].append(action)

    # Extract PM tool configuration
    pm_section = extract_section(content, "Project Management")
    if pm_section:
        tool_match = re.search(r'\*\*Configured Tool\*\*:\s*(\w+)', pm_section, re.IGNORECASE)
        if tool_match:
            tool = tool_match.group(1).lower()
            if tool in ['linear', 'github', 'jira', 'gitlab']:
                customizations["pm_tool"] = tool

    # Legacy view of the custom sections: every `##` header the lists above
    # do not render (nor the section that carries the runtime paragraph),
    # with the standard section that follows it as the anchor.
    titles = [s["header"] for s in customizations["sections"]]
    owned = set(STANDARD_SECTIONS) | {customizations["navigator_section"]}
    for index, section in enumerate(customizations["sections"]):
        header, body = section["header"], section["body"]
        if header in owned or not body.strip():
            continue
        customizations["custom_sections"][header] = body
        anchor = next((h for h in titles[index + 1:] if h in STANDARD_SECTIONS), None)
        customizations["custom_section_anchors"][header] = anchor

    return customizations


def _replace_section_body(text: str, header: str, body: str) -> str:
    """Replace the body under `## header` (up to the next header) with `body`."""
    headers = _scan_headers(text)
    for index, (level, title, _start, end) in enumerate(headers):
        if level != 2 or title != header:
            continue
        if index + 1 < len(headers):
            next_start = headers[index + 1][2]
            return text[:end] + '\n' + body + '\n\n' + text[next_start:]
        return text[:end] + '\n' + body + '\n'
    return text


def _replace_field_line(text: str, field: str, value: str) -> str:
    """Replace the whole `**Field**: ...` line (single line) with `value`."""
    pattern = re.compile(r'^\*\*' + re.escape(field) + r'\*\*:.*$', re.MULTILINE)
    return pattern.sub(lambda _m: f'**{field}**: {value}', text, count=1)


def _insert_custom_sections(text: str, sections: Dict[str, str],
                            anchors: Dict[str, Optional[str]]) -> str:
    """Put each custom section back before its anchor, else at the end."""
    for name, body in sections.items():
        block = f"## {name}\n\n{body}\n\n"
        anchor = anchors.get(name)
        anchor_start = None
        if anchor:
            anchor_start = next((start for level, title, start, _end in _scan_headers(text)
                                 if level == 2 and title == anchor), None)
        if anchor_start is not None:
            text = text[:anchor_start] + block + text[anchor_start:]
        else:
            text = text.rstrip('\n') + '\n\n' + block.rstrip('\n') + '\n'
    return text


def stamp_lines(text: str, version: Optional[str], today: str) -> str:
    """Stamp **Last Updated** with `today` and **Navigator Version** with `version`."""
    text = _replace_field_line(text, "Last Updated", today)
    if version:
        text = _replace_field_line(text, "Navigator Version", version)
    return text


def _render_from_lists(customizations: Dict, template: str) -> str:
    """Legacy path: the template's structure around the flat lists."""
    if customizations.get("project_name"):
        template = template.replace('[Project Name]', customizations["project_name"])

    if customizations.get("description"):
        template = template.replace(DESCRIPTION_PLACEHOLDER, customizations["description"])

    if customizations.get("tech_stack"):
        template = template.replace(
            TECH_STACK_PLACEHOLDER, ', '.join(customizations["tech_stack"]))

    if customizations.get("core_principle"):
        template = _replace_field_line(
            template, "Core Principle", customizations["core_principle"])

    # Code standards: the project's list replaces the template's list and
    # the "[Customize ...]" placeholder. An empty list keeps the template's.
    if customizations.get("code_standards"):
        body = '\n'.join(f"- {s}" for s in customizations["code_standards"])
        template = _replace_section_body(template, "Project-Specific Code Standards", body)

    # Forbidden actions: same rule; the violations marker survives only when
    # the project's file carried it (or when the template's list is kept).
    if customizations.get("forbidden_actions"):
        body = '\n'.join(f"- ❌ {a}" for a in customizations["forbidden_actions"])
        if customizations.get("violations_marker"):
            body += f"\n\n{VIOLATIONS_MARKER}"
        template = _replace_section_body(template, "Forbidden Actions", body)

    if customizations.get("pm_tool", "none") != "none":
        template = template.replace(
            '**Configured Tool**: [Linear / GitHub Issues / Jira / GitLab / None]',
            f'**Configured Tool**: {customizations["pm_tool"].title()}'
        )
        template = template.replace(
            '"project_management": "none"',
            f'"project_management": "{customizations["pm_tool"]}"'
        )

    # Custom sections go back where they were (before the standard section
    # that followed them); sections without an anchor go to the end.
    if customizations.get("custom_sections"):
        template = _insert_custom_sections(
            template, customizations["custom_sections"],
            customizations.get("custom_section_anchors") or {})
    return template


def _render_from_layout(customizations: Dict, template: str) -> str:
    """Layout path: the project's title, preamble and sections in their own
    order; only Navigator-owned text comes from the template."""
    template_sections = [
        (title, body) for level, title, body in _section_bodies(template) if level == 2]
    template_bodies = dict(template_sections)
    template_navigator = template_bodies.get("Navigator", "")
    template_paragraph = template_navigator
    span = _runtime_paragraph_span(template_navigator)
    if span:
        template_paragraph = template_navigator[span[0]:span[1]]

    title = customizations.get("title") or ""
    if not title:
        template_h1 = next((h for h in _scan_headers(template) if h[0] == 1), None)
        title = template_h1[1] if template_h1 else "[Project Name] - Claude Code Configuration"
        if customizations.get("project_name"):
            title = title.replace("[Project Name]", customizations["project_name"])

    blocks: List[Tuple[str, str]] = []  # (header or '' for the preamble, body)
    if customizations.get("preamble"):
        blocks.append(("", customizations["preamble"]))

    owner = customizations.get("navigator_section") or ""
    for section in customizations.get("sections") or []:
        header, body = section["header"], section["body"]
        if header.lower() == "navigator" and template_navigator:
            body = template_navigator
        elif header == owner and template_paragraph:
            span = _runtime_paragraph_span(body)
            if span:
                body = body[:span[0]] + template_paragraph + body[span[1]:]
        blocks.append((header, body))

    present = {header.lower() for header, _body in blocks if header}
    for owned, aliases in SECTION_ALIASES.items():
        if any(alias.lower() in present for alias in aliases):
            present.add(owned.lower())
    has_stamps = any(
        re.search(r'^\*\*' + re.escape(f) + r'\*\*:', body, re.MULTILINE)
        for _h, body in blocks for f in STAMP_FIELDS)

    def insert_after_owned(header: str, body: str) -> None:
        """Add a template section the project lacks, right after the last
        template section that precedes it in template order and is present;
        at the top when none is."""
        order = [t for t, _b in template_sections]
        preceding = {t.lower() for t in order[:order.index(header)]}
        for owned, aliases in SECTION_ALIASES.items():
            if owned.lower() in preceding:
                preceding.update(a.lower() for a in aliases)
        position = 1 if blocks and not blocks[0][0] else 0  # after the preamble
        for index, (h, _b) in enumerate(blocks):
            if h and h.lower() in preceding:
                position = index + 1
        blocks.insert(position, (header, body))

    for header, body in template_sections:
        if header.lower() in present:
            continue
        if header == "Context":
            if has_stamps:
                continue  # the project keeps its stamps elsewhere; no placeholders
            body = '\n'.join(f"**{f}**: " for f in STAMP_FIELDS)
        elif header == "Navigator" and owner:
            continue  # the runtime paragraph lives in the project's own section
        insert_after_owned(header, body)
        present.add(header.lower())

    parts = [f"# {title}"]
    for header, body in blocks:
        parts.append(f"## {header}\n\n{body}" if header else body)
    return '\n\n'.join(parts) + '\n'


def generate_updated_claude_md(customizations: Dict, template_path: str, output_path: str,
                               version: Optional[str] = None,
                               today: Optional[str] = None):
    """Generate CLAUDE.md. With a `sections` layout (what `extract` records)
    the project's own layout is rendered and only Navigator-owned text is
    replaced; without one the template's structure is rendered around the
    flat lists. `version` defaults to the plugin this script ships with;
    `today` to the local date (both injectable for tests)."""

    with open(template_path, 'r', encoding='utf-8') as f:
        template = f.read()

    if customizations.get("sections"):
        text = _render_from_layout(customizations, template)
    else:
        text = _render_from_lists(customizations, template)

    text = stamp_lines(
        text,
        version if version is not None else installed_plugin_version(),
        today if today is not None else datetime.now().date().isoformat(),
    )

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(text)


def resolve_project_root(explicit: Optional[str], customizations: Dict) -> Path:
    """Project root for the liveness guard: --project-root, else the
    directory `extract` read CLAUDE.md from, else the current directory.
    Never the --output path: a dry run may write anywhere."""
    if explicit:
        return Path(explicit).resolve()
    source_dir = customizations.get("source_dir")
    if isinstance(source_dir, str) and source_dir:
        return Path(source_dir).resolve()
    return Path.cwd().resolve()


def main():
    if len(sys.argv) < 3:
        print("Usage:", file=sys.stderr)
        print("  Extract: python3 claude_updater.py extract CLAUDE.md > customizations.json", file=sys.stderr)
        print("  Generate: python3 claude_updater.py generate --customizations file.json --template template.md --output CLAUDE.md [--project-root DIR] [--stamp-version X.Y.Z] [--stamp-date YYYY-MM-DD]", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]

    if command == "extract":
        claude_md_path = sys.argv[2]

        if not Path(claude_md_path).exists():
            print(f"Error: File not found: {claude_md_path}", file=sys.stderr)
            sys.exit(1)

        try:
            customizations = extract_customizations(claude_md_path)
            print(json.dumps(customizations, indent=2))
        except Exception as e:
            print(f"Error extracting customizations: {e}", file=sys.stderr)
            sys.exit(2)

    elif command == "generate":
        # Parse arguments
        args = {
            'customizations': None,
            'template': None,
            'output': None,
        }
        optional = {'project_root': None, 'stamp_version': None, 'stamp_date': None}
        flags = {
            '--customizations': 'customizations', '--template': 'template',
            '--output': 'output', '--project-root': 'project_root',
            '--stamp-version': 'stamp_version', '--stamp-date': 'stamp_date',
        }

        i = 2
        while i < len(sys.argv):
            key = flags.get(sys.argv[i])
            if key and i + 1 < len(sys.argv):
                (args if key in args else optional)[key] = sys.argv[i + 1]
                i += 2
            else:
                i += 1

        if not all(args.values()):
            print("Error: Missing required arguments", file=sys.stderr)
            print("Required: --customizations, --template, --output", file=sys.stderr)
            sys.exit(1)

        try:
            with open(args['customizations'], 'r') as f:
                customizations = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"Error reading customizations: {e}", file=sys.stderr)
            sys.exit(2)

        # TASK-63 Phase 5: regeneration only after observed hook liveness.
        # Runs before any template fetch/read so a refusal is side-effect free.
        # The root is the project, never the --output path (a dry run may
        # write to /tmp).
        project_root = resolve_project_root(optional['project_root'], customizations)
        alive, guard_message = check_hook_liveness(project_root)
        if not alive:
            print(guard_message, file=sys.stderr)
            sys.exit(3)

        try:
            # Use get_template_path for GitHub fetch with bundled fallback
            # If --template is a directory, treat it as bundled_template_dir
            # Otherwise, use it directly as a file path
            template_arg = args['template']

            if Path(template_arg).is_dir():
                # Directory provided - use get_template_path for smart fetching
                template_path, is_github = get_template_path(template_arg)
            elif Path(template_arg).is_file():
                # File provided directly - use as-is (backward compatibility)
                template_path = template_arg
                is_github = False
            else:
                # Try parent directory for get_template_path
                template_dir = str(Path(template_arg).parent)
                template_path, is_github = get_template_path(template_dir)

            generate_updated_claude_md(
                customizations, template_path, args['output'],
                version=optional['stamp_version'], today=optional['stamp_date'])
            print(f"✓ Generated {args['output']}", file=sys.stderr)

            # Cleanup temp file if from GitHub
            if is_github and Path(template_path).exists():
                Path(template_path).unlink()

        except Exception as e:
            print(f"Error generating CLAUDE.md: {e}", file=sys.stderr)
            sys.exit(2)

    else:
        print(f"Error: Unknown command: {command}", file=sys.stderr)
        print("Valid commands: extract, generate", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
