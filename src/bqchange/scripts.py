"""Discovery and ordering of migration scripts.

Naming follows schemachange:
    V<version>__<description>.sql   versioned, applied once, in version order
    R__<description>.sql            repeatable, re-applied when the rendered content changes
    A__<description>.sql            always, applied on every deployment
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

_PATTERNS = {
    "V": re.compile(
        r"^V(?P<version>\d+(?:[._]\d+)*)__(?P<description>.+?)\.sql(?:\.jinja)?$", re.I
    ),
    "R": re.compile(r"^R__(?P<description>.+?)\.sql(?:\.jinja)?$", re.I),
    "A": re.compile(r"^A__(?P<description>.+?)\.sql(?:\.jinja)?$", re.I),
}


class ScriptType(StrEnum):
    VERSIONED = "V"
    REPEATABLE = "R"
    ALWAYS = "A"


@dataclass(frozen=True)
class Script:
    name: str
    relative_path: str
    script_type: ScriptType
    description: str
    version: str | None = None

    @property
    def version_key(self) -> tuple[int, ...]:
        return parse_version(self.version) if self.version else ()


def parse_version(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.split(r"[._]", version))


def discover(root: Path) -> list[Script]:
    """Find every script under root, ordered for execution: V by version, then R, then A by name."""
    scripts: list[Script] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        for script_type, pattern in _PATTERNS.items():
            match = pattern.match(path.name)
            if match:
                scripts.append(
                    Script(
                        name=path.name,
                        relative_path=path.relative_to(root).as_posix(),
                        script_type=ScriptType(script_type),
                        description=match["description"].replace("_", " "),
                        version=match.groupdict().get("version"),
                    )
                )
                break

    names = [script.name for script in scripts]
    if duplicates := sorted({name for name in names if names.count(name) > 1}):
        raise ValueError(f"Duplicate script names: {duplicates}")
    versions = [script.version_key for script in scripts if script.version]
    if duplicates := sorted({v for v in versions if versions.count(v) > 1}):
        raise ValueError(f"Duplicate versions: {['.'.join(map(str, v)) for v in duplicates]}")

    order = {ScriptType.VERSIONED: 0, ScriptType.REPEATABLE: 1, ScriptType.ALWAYS: 2}
    return sorted(scripts, key=lambda s: (order[s.script_type], s.version_key, s.name))
