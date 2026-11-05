"""`CHANGELOG.md` as data for the panel's „Co nowego" page.

Only the subset the changelog uses: `## [X.Y.Z] — date` opens a version, `### Group` a group,
`- ` an item (indented lines continue it), anything else is an intro paragraph; inline
`**bold**` and `` `code` ``. The text is escaped first and only those two marks become HTML,
so nothing in the file can inject markup. Everything before the first version (the file's
own introduction, written for developers) is skipped.
"""

import re
from dataclasses import dataclass, field

from django.utils.html import escape
from django.utils.safestring import mark_safe

from core.version import CHANGELOG

VERSION = re.compile(r"^## \[(?P<version>[^\]]+)\]\s*(?:[—–-]\s*(?P<date>.+))?$")
GROUP = re.compile(r"^### (?P<title>.+)$")
BOLD = re.compile(r"\*\*(.+?)\*\*")
CODE = re.compile(r"`(.+?)`")


def inline(text):
    html = escape(text)
    html = BOLD.sub(r"<strong>\1</strong>", html)
    html = CODE.sub(r"<code>\1</code>", html)
    return mark_safe(html)  # noqa: S308 — escaped above; only <strong>/<code> are added


@dataclass
class Group:
    title: str
    items: list = field(default_factory=list)


@dataclass
class Release:
    version: str
    date: str
    intro: list = field(default_factory=list)
    groups: list = field(default_factory=list)


def parse_changelog(text):
    releases = []
    release = group = None
    # Lines of the item or paragraph being read; flushed by a blank line or a new block.
    buffer, kind = [], None

    def flush():
        nonlocal buffer, kind
        if buffer and release is not None:
            joined = inline(" ".join(buffer))
            if kind == "item":
                (group or release_group()).items.append(joined)
            else:
                release.intro.append(joined)
        buffer, kind = [], None

    def release_group():
        # An item before any "### Group": give it an untitled group of its own.
        nonlocal group
        group = Group(title="")
        release.groups.append(group)
        return group

    for raw in text.splitlines():
        line = raw.rstrip()
        version = VERSION.match(line)
        if version:
            flush()
            release = Release(version=version["version"], date=(version["date"] or "").strip())
            releases.append(release)
            group = None
            continue
        if release is None:
            continue  # the file's introduction
        heading = GROUP.match(line)
        if heading:
            flush()
            group = Group(title=heading["title"].strip())
            release.groups.append(group)
        elif line.startswith("- "):
            flush()
            buffer, kind = [line[2:].strip()], "item"
        elif not line.strip():
            flush()
        elif kind == "item" and raw[:1].isspace():
            buffer.append(line.strip())
        else:
            if kind == "item":
                flush()
            buffer.append(line.strip())
            kind = "paragraph"
    flush()
    return releases


def load_changelog():
    return parse_changelog(CHANGELOG.read_text(encoding="utf-8"))
