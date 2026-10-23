"""Parsing helpers for upstream documentation sources.

Pure Python (no frappe import) so it can be unit-tested anywhere.

Upstream wiki spaces publish a nested index at ``<space>/llms.txt``::

    - [Introduction](https://docs.example.io/erpnext/introduction.md)
      - [Why ERP?](https://docs.example.io/erpnext/why-ERP.md)
    - **Setup**
      - [Company](https://docs.example.io/erpnext/company-setup.md): Short description
      - [Chart Of Accounts Importer](<https://docs.example.io/erpnext/chart-of-accounts-importer>)

and every page as raw markdown at ``<page-url>.md`` with YAML-ish front matter.
"""

import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit

_ITEM_RE = re.compile(r"^(?P<indent>[ \t]*)[-*] (?P<body>.+?)\s*$")
_GROUP_RE = re.compile(r"^\*\*(?P<label>.+?)\*\*$")
_LINK_RE = re.compile(
    r"^\[(?P<label>(?:\\.|[^\]\\])+)\]\((?P<url><[^>]+>|[^)]+)\)(?::\s*(?P<desc>.*))?$"
)


def normalize_slug(value):
    """Turn an upstream path (``Selling-in-different-UOM.md``) into our slug (``selling-in-different-uom``)."""
    s = unquote(value or "").strip().strip("/")
    s = re.sub(r"\.md$", "", s, flags=re.I)
    s = s.lower()
    s = re.sub(r"[^a-z0-9/_-]+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    s = re.sub(r"/{2,}", "/", s)
    s = "/".join(part.strip("-") for part in s.split("/"))
    return s.strip("/-")


def _unescape(label):
    return re.sub(r"\\(.)", r"\1", label).strip()


@dataclass
class IndexNode:
    title: str
    url: str = None
    angle: bool = False  # url was written as <...> (a reference, not a .md source)
    description: str = None
    depth: int = 0
    children: list = field(default_factory=list)


def parse_llms_index(text):
    """Parse an llms.txt nested list into a forest of IndexNode."""
    roots, stack = [], []
    for raw in (text or "").splitlines():
        m = _ITEM_RE.match(raw)
        if not m:
            continue
        depth = len(m.group("indent").expandtabs(2)) // 2
        body = m.group("body")
        node = None
        g = _GROUP_RE.match(body)
        if g:
            node = IndexNode(title=_unescape(g.group("label")), depth=depth)
        else:
            lk = _LINK_RE.match(body)
            if not lk:
                continue
            url = lk.group("url").strip()
            angle = url.startswith("<") and url.endswith(">")
            if angle:
                url = url[1:-1].strip()
            node = IndexNode(
                title=_unescape(lk.group("label")),
                url=url,
                angle=angle,
                description=(lk.group("desc") or "").strip() or None,
                depth=depth,
            )
        while stack and stack[-1].depth >= depth:
            stack.pop()
        if stack:
            stack[-1].children.append(node)
        else:
            roots.append(node)
        stack.append(node)
    return roots


def source_slug(url, base_url):
    """Return our normalized slug for an upstream URL, or None if outside base_url."""
    if not url:
        return None
    base = (base_url or "").rstrip("/")
    u = url.split("#", 1)[0].split("?", 1)[0]
    if base and u.startswith(base + "/"):
        return normalize_slug(u[len(base) + 1:])
    # relative path form, e.g. /erpnext/sales-invoice
    base_path = urlsplit(base).path.rstrip("/") if base else ""
    if base_path and u.startswith(base_path + "/"):
        return normalize_slug(u[len(base_path) + 1:])
    return None


def plan_import(roots, base_url):
    """Flatten the index into an ordered list of items to upsert.

    Each item: dict(key, type: Page|Group|Link, title, parent, sort, description,
    fetch_url, slug, target_slug, external_url)

    * A node with children becomes a Group. If the node's own URL is not repeated
      among its descendants, an extra first-child Page is created for it.
    * The first occurrence of a .md URL becomes a Page; later ones become Links.
    * ``<...>`` references become Links resolved by slug after all pages exist.
    """
    items, seen_pages = [], set()

    def subtree_slugs(node):
        out = set()
        for c in node.children:
            s = source_slug(c.url, base_url)
            if s:
                out.add(s)
            out |= subtree_slugs(c)
        return out

    def path_key(parts):
        return "/".join(normalize_slug(p) or "x" for p in parts)

    def emit_leaf(node, parent_key, parent_path, sort):
        slug = source_slug(node.url, base_url)
        is_source_md = bool(node.url) and not node.angle and node.url.lower().endswith(".md")
        if slug and is_source_md and slug not in seen_pages:
            seen_pages.add(slug)
            items.append(dict(key="page:" + slug, type="Page", title=node.title, parent=parent_key,
                              sort=sort, description=node.description, fetch_url=node.url, slug=slug))
            return
        key = "link:" + path_key(parent_path + [node.title])
        if slug:
            items.append(dict(key=key, type="Link", title=node.title, parent=parent_key, sort=sort,
                              description=node.description, target_slug=slug))
        elif node.url:
            items.append(dict(key=key, type="Link", title=node.title, parent=parent_key, sort=sort,
                              description=node.description, external_url=node.url))

    def walk(nodes, parent_key, parent_path):
        for idx, node in enumerate(nodes):
            sort = (idx + 1) * 10
            if node.children or not node.url:
                path = parent_path + [node.title]
                gkey = "group:" + path_key(path)
                items.append(dict(key=gkey, type="Group", title=node.title, parent=parent_key,
                                  sort=sort, description=node.description))
                own = source_slug(node.url, base_url)
                if own and own not in subtree_slugs(node):
                    emit_leaf(IndexNode(title=node.title, url=node.url, angle=node.angle,
                                        description=node.description), gkey, path, 5)
                walk(node.children, gkey, path)
            else:
                emit_leaf(node, parent_key, parent_path, sort)

    walk(roots, None, [])
    return items


_FM_RE = re.compile(r"^﻿?---[ \t]*\r?\n(?P<fm>.*?)\r?\n---[ \t]*\r?\n?", re.S)


def split_frontmatter(text):
    """Return (meta: dict, body: str). Handles simple ``key: "value"`` front matter."""
    text = text or ""
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group("fm").splitlines():
        if ":" not in line or line.startswith((" ", "\t", "#")):
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1].replace('\\"', '"')
        meta[k.strip()] = v
    return meta, text[m.end():].lstrip("\n")


def strip_leading_h1(body, title):
    """Drop a leading '# Title' heading when it repeats the page title."""
    m = re.match(r"^\s*#\s+(.+?)\s*#*\s*\n", body or "")
    if m and title and m.group(1).strip().lower() == title.strip().lower():
        return body[m.end():].lstrip("\n")
    return body
