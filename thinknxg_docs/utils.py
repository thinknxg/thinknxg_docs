"""Shared helpers: caching, navigation tree, markdown rendering, rebrander factory."""

import html as html_lib
import re

import frappe
from frappe.utils import cint

from thinknxg_docs.rebrand import Rebrander

CACHE_PREFIX = "thinknxg_docs"
TREE_KEY = CACHE_PREFIX + ":tree:"
ROUTES_KEY = CACHE_PREFIX + ":space_routes"
HTML_KEY = CACHE_PREFIX + ":html:"
VIEWS_KEY = CACHE_PREFIX + ":views"
ROOT_LABEL = "All Pages"

RESERVED_ROUTES = {
    "app", "api", "assets", "files", "private", "login", "logout", "me", "desk", "socket.io",
    "update-password", "update-profile", "website_script.js", "robots.txt", "sitemap.xml",
    "llms.txt", "docs-sitemap.xml", "list", "print", "printview", "message", "contact", "about",
    "blog", "search", "third_party_apps", "apps", "unsubscribe", "qrcode", "error", "404",
    "index", "home", "portal", "website", "web", "method",
}


def cache():
    c = frappe.cache
    return c() if callable(c) and not hasattr(c, "get_value") else c


def get_settings():
    return frappe.get_cached_doc("Docs Settings")


def clear_cache(space=None):
    c = cache()
    try:
        names = [space] if space else get_space_routes(refresh=True)
        c.delete_value([TREE_KEY + s for s in names] + [ROUTES_KEY])
    except Exception:
        frappe.log_error(title="thinkNXG Docs: cache clear failed")
    frappe.local.thinknxg_docs_rebrander = None


# --------------------------------------------------------------------- spaces
def get_space_routes(refresh=False):
    c = cache()
    routes = None if refresh else c.get_value(ROUTES_KEY)
    if routes is None:
        routes = frappe.get_all("Docs Space", pluck="name") if frappe.db.table_exists("Docs Space") else []
        c.set_value(ROUTES_KEY, routes, expires_in_sec=86400)
    return routes


def get_switcher_spaces(current=None, include_unpublished=False):
    filters = {"show_in_switcher": 1}
    if not include_unpublished:
        filters["published"] = 1
    rows = frappe.get_all("Docs Space", filters=filters, fields=["name", "title", "description", "published"],
                          order_by="sort_order asc, title asc")
    for r in rows:
        r.url = "/" + r.name
        r.active = r.name == current
    return rows


# ------------------------------------------------------------------- rebrand
def get_rebrander():
    cached = getattr(frappe.local, "thinknxg_docs_rebrander", None)
    if cached:
        return cached
    settings = get_settings()
    text_rules, url_rules = [], []
    for row in settings.get("rebrand_rules") or []:
        if not cint(row.enabled) or not row.find_text:
            continue
        if row.rule_type == "URL":
            url_rules.append((row.find_text.strip(), (row.replace_with or "").strip()))
        else:
            text_rules.append((row.find_text, row.replace_with or "", cint(row.match_case), cint(row.whole_word)))
    space_maps = []
    for sp in frappe.get_all("Docs Space", fields=["name", "source_base_url"]):
        base = (sp.source_base_url or "").rstrip("/")
        if base:
            space_maps.append((base, "/" + sp.name))
    r = Rebrander(text_rules=text_rules, url_rules=url_rules, space_maps=space_maps,
                  slug_resolver=make_slug_resolver())
    frappe.local.thinknxg_docs_rebrander = r
    return r


def make_slug_resolver(extra=None):
    """Resolve slugs that moved: exact → unique last-segment match → unchanged."""
    known = {}

    def load(route):
        if route not in known:
            slugs = set(frappe.get_all("Docs Page", filters={"space": route, "page_type": "Page"}, pluck="slug"))
            slugs |= set((extra or {}).get(route, ()))
            known[route] = slugs
        return known[route]

    def resolve(target, slug):
        route = (target or "").strip("/")
        if not route:
            return slug
        slugs = load(route)
        if not slugs or slug in slugs:
            return slug
        last = slug.rsplit("/", 1)[-1]
        if last in slugs:
            return last
        cands = [s for s in slugs if s.endswith("/" + last)]
        return cands[0] if len(cands) == 1 else slug

    return resolve


def rebrand_on_save_enabled():
    try:
        return cint(get_settings().rebrand_on_save)
    except Exception:
        return 0


# ---------------------------------------------------------------------- tree
def get_tree(space):
    """Return {"tree": [...], "flat": [...], "ancestors": {name: [labels]}, "open": {name: [names]},
    "by_slug": {slug: name}} for a space. Cached until a page/space changes."""
    c = cache()
    key = TREE_KEY + space
    data = c.get_value(key)
    if data:
        return data

    rows = frappe.get_all(
        "Docs Page",
        filters={"space": space, "published": 1},
        fields=["name", "title", "sidebar_label", "page_type", "parent_docs_page", "slug", "route",
                "sort_order", "lft", "link_to_page", "external_url"],
        order_by="lft asc",
        limit_page_length=0,
    )
    by_name = {r.name: r for r in rows}
    link_targets = [r.link_to_page for r in rows if r.page_type == "Link" and r.link_to_page]
    target_routes = {}
    if link_targets:
        for t in frappe.get_all("Docs Page", filters={"name": ("in", link_targets), "published": 1},
                                fields=["name", "route"]):
            target_routes[t.name] = t.route

    nodes = {}
    for r in rows:
        n = {"name": r.name, "label": r.sidebar_label or r.title, "type": r.page_type,
             "sort": (cint(r.sort_order), cint(r.lft)), "children": [], "url": None, "external": 0}
        if r.page_type == "Page":
            n["url"] = "/" + (r.route or "")
        elif r.page_type == "Link":
            if r.link_to_page and target_routes.get(r.link_to_page):
                n["url"] = "/" + target_routes[r.link_to_page]
                n["target"] = r.link_to_page
            elif r.external_url:
                n["url"] = r.external_url
                n["external"] = 0 if r.external_url.startswith("/") else 1
            else:
                continue
        nodes[r.name] = n

    roots = []
    for r in rows:
        n = nodes.get(r.name)
        if not n:
            continue
        parent = nodes.get(r.parent_docs_page) if r.parent_docs_page else None
        (parent["children"] if parent else roots).append(n)

    def prune(items):
        out = []
        for n in sorted(items, key=lambda x: x["sort"]):
            n["children"] = prune(n["children"])
            n.pop("sort", None)
            if n["type"] == "Group" and not n["children"]:
                continue
            out.append(n)
        return out

    roots = prune(roots)

    flat, ancestors, open_map = [], {}, {}

    def walk(items, labels, names):
        for n in items:
            if n["type"] == "Page":
                flat.append({"name": n["name"], "label": n["label"], "url": n["url"]})
                ancestors[n["name"]] = labels
                open_map[n["name"]] = names
            if n["children"]:
                walk(n["children"], labels + [n["label"]], names + [n["name"]])

    walk(roots, [], [])
    by_slug = {r.slug: r.name for r in rows if r.page_type == "Page" and r.slug}
    data = {"tree": roots, "flat": flat, "ancestors": ancestors, "open": open_map, "by_slug": by_slug}
    c.set_value(key, data, expires_in_sec=86400)
    return data


# ------------------------------------------------------------------ markdown
_HEADING_RE = re.compile(r"<h([23])([^>]*)>(.*?)</h\1>", re.S | re.I)
_ID_RE = re.compile(r'\bid="([^"]+)"')
_TAG_RE = re.compile(r"<[^>]+>")


def _slugify(text):
    s = re.sub(r"[^\w\s-]", "", text, flags=re.U).strip().lower()
    return re.sub(r"[\s_-]+", "-", s) or "section"


def render_markdown(name, modified, content):
    """Markdown → HTML (cached per page+modified) and a TOC list [(level, id, text)]."""
    c = cache()
    key = f"{HTML_KEY}{name}:{modified}"
    hit = c.get_value(key)
    if hit:
        return hit["html"], hit["toc"]
    html = _md(content or "")
    toc, used = [], set()

    def fix(m):
        level, attrs, inner = m.group(1), m.group(2), m.group(3)
        text = html_lib.unescape(_TAG_RE.sub("", inner)).strip()
        idm = _ID_RE.search(attrs)
        hid = idm.group(1) if idm else _slugify(text)
        base, i = hid, 2
        while hid in used:
            hid, i = f"{base}-{i}", i + 1
        used.add(hid)
        attrs = _ID_RE.sub("", attrs)
        toc.append({"level": int(level), "id": hid, "text": text})
        return (f'<h{level}{attrs} id="{hid}">{inner}'
                f'<a class="heading-anchor" href="#{hid}" aria-label="Link to this section">#</a></h{level}>')

    html = _HEADING_RE.sub(fix, html)
    html = re.sub(r"<table", '<div class="table-wrap"><table', html)
    html = re.sub(r"</table>", "</table></div>", html)
    html = re.sub(r"<img(?![^>]*\bloading=)", '<img loading="lazy"', html)
    c.set_value(key, {"html": html, "toc": toc}, expires_in_sec=86400)
    return html, toc


def _md(text):
    try:
        from markdown2 import markdown

        return str(markdown(text, extras={
            "fenced-code-blocks": None, "tables": None, "header-ids": None, "strike": None,
            "task_list": None, "highlightjs-lang": None, "cuddled-lists": None, "footnotes": None,
        }))
    except Exception:
        from frappe.utils import md_to_html

        return str(md_to_html(text) or "")


def markdown_to_plain(text):
    t = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"[#>*_`|~-]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def public_base_url():
    base = (get_settings().docs_base_url or "").strip().rstrip("/")
    return base or frappe.utils.get_url().rstrip("/")
