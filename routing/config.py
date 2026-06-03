"""claude-orch-shell config / shell registry loader (claude-orch-shell SPEC §5.1).

Loads `orch.config.yml`: the `target_repo` whose Initiative metadata is routed, the
`shells` registry (path + invoke recipe per shell), and the `auto_invoke` flag.

A MINIMAL line parser — NOT a general YAML library (no PyYAML dependency). It
understands exactly the SPEC §5.1 shape (flat scalars + one `shells:` block of
`name:` → `path:`/`invoke:`). Swapping in a real YAML parser is a deferred Tier-2
choice (SPEC §9 "Config format/location").

Python 3 stdlib only. See routing/README.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

_BOOL_TRUE = {"true", "yes", "on", "1"}
_BOOL_FALSE = {"false", "no", "off", "0"}
_COMMENT = re.compile(r"\s+#.*$")


@dataclass(frozen=True)
class ShellEntry:
    path: str
    invoke: Optional[str] = None   # None / "null" → not invoked (e.g. res, SPEC §5.1)


@dataclass(frozen=True)
class OrchConfig:
    target_repo: Optional[str] = None
    auto_invoke: bool = False
    shells: dict[str, ShellEntry] = field(default_factory=dict)


def _strip(line: str) -> str:
    return _COMMENT.sub("", line.rstrip("\n")).rstrip()


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        return v[1:-1]
    return v


def _as_bool(v: str, *, default: bool = False) -> bool:
    s = v.strip().lower()
    if s in _BOOL_TRUE:
        return True
    if s in _BOOL_FALSE:
        return False
    return default


def _scalar_or_none(v: str) -> Optional[str]:
    s = _unquote(v)
    if s == "" or s.lower() in ("null", "~", "none"):
        return None
    return s


def load_config(text: str) -> OrchConfig:
    """Parse `orch.config.yml` content into an OrchConfig (SPEC §5.1)."""
    target_repo: Optional[str] = None
    auto_invoke = False
    shells: dict[str, ShellEntry] = {}

    in_shells = False
    cur_shell: Optional[str] = None
    cur_path: Optional[str] = None
    cur_invoke: Optional[str] = None

    def _flush_shell() -> None:
        nonlocal cur_shell, cur_path, cur_invoke
        if cur_shell is not None:
            shells[cur_shell] = ShellEntry(path=cur_path or "", invoke=cur_invoke)
        cur_shell = cur_path = cur_invoke = None

    for raw in text.splitlines():
        line = _strip(raw)
        if not line.strip():
            continue
        indent = _indent(line)
        key, _, val = line.strip().partition(":")
        key = key.strip()

        if indent == 0:
            _flush_shell()
            in_shells = False
            if key == "target_repo":
                target_repo = _scalar_or_none(val)
            elif key == "auto_invoke":
                auto_invoke = _as_bool(val)
            elif key == "shells":
                in_shells = True
            # unknown top-level keys are ignored (forward-compatible)
        elif in_shells and indent == 2:
            # a new shell name (value is empty: "dir:")
            _flush_shell()
            cur_shell = key
        elif in_shells and indent >= 4 and cur_shell is not None:
            if key == "path":
                cur_path = _scalar_or_none(val)
            elif key == "invoke":
                cur_invoke = _scalar_or_none(val)
        # everything else ignored

    _flush_shell()
    return OrchConfig(target_repo=target_repo, auto_invoke=auto_invoke, shells=shells)


def load_config_file(path: str) -> OrchConfig:
    with open(path, "r", encoding="utf-8") as fh:
        return load_config(fh.read())
