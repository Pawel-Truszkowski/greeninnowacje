"""Which version of the app is this, and what changed in it.

One source of truth: `version` in `pyproject.toml` (mirrored in `uv.lock` by `uv lock`).
The major number is Greenowacje's prototype — 2.x is „Prototyp drugi"; a fix bumps the last
number, a feature the middle one. What changed lives in `CHANGELOG.md`, one `## [X.Y.Z]`
section per version; `core/tests/test_versioning.py` fails when the two disagree.

The commit and build time are baked into the image by CI (`Dockerfile` build args), so a
running container can say exactly what it is; locally they read "dev".

Standard library only: CI runs this file directly, without installing Django —
`python3 core/version.py` prints the release notes, `--version` just the number.
"""

import os
import re
import tomllib
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PYPROJECT = BASE_DIR / "pyproject.toml"
CHANGELOG = BASE_DIR / "CHANGELOG.md"

# "## [2.0.0] — 2026-11-04": the version in brackets opens a section.
HEADING = re.compile(r"^## \[(?P<version>[^\]]+)\]")


def read_version(path=PYPROJECT):
    with open(path, "rb") as file:
        return tomllib.load(file)["project"]["version"]


def changelog_section(text, version):
    """The body of `version`'s section, without its heading; None when there is none."""
    lines, inside = [], False
    for line in text.splitlines():
        heading = HEADING.match(line)
        if heading:
            if inside:
                break
            inside = heading["version"] == version
            continue
        if inside:
            lines.append(line)
    return "\n".join(lines).strip() if inside else None


APP_VERSION = read_version()
APP_COMMIT = os.environ.get("APP_COMMIT") or "dev"
APP_BUILT_AT = os.environ.get("APP_BUILT_AT") or ""


if __name__ == "__main__":
    import sys

    if "--version" in sys.argv:  # for CI: the image tag and the release name
        print(APP_VERSION)
        raise SystemExit
    notes = changelog_section(CHANGELOG.read_text(encoding="utf-8"), APP_VERSION)
    if notes is None:
        raise SystemExit(f"CHANGELOG.md nie ma sekcji dla wersji {APP_VERSION}.")
    print(notes)
