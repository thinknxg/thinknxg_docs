"""Website renderer for docs spaces.

Registered via ``page_renderer`` in hooks.py and checked before Frappe's own renderers.

Routes (for a space with route ``thinknxgerp``):
  /thinknxgerp                 → space home page
  /thinknxgerp/<slug>          → page (slug may contain "/")
  /thinknxgerp/<slug>.md       → raw markdown with front matter
  /thinknxgerp/llms.txt        → nested index of the space
  /thinknxgerp/sitemap.xml     → sitemap of the space
  /llms.txt                    → index of all published spaces
  /docs-sitemap.xml            → sitemap index of all published spaces
"""

import json
from urllib.parse import quote
from xml.sax.saxutils import escape as xml_escape

import frappe
from frappe import _
from frappe.utils import cint, getdate, pretty_date
from frappe.website.page_renderers.base_renderer import BaseRenderer
from werkzeug.wrappers import Response

from thinknxg_docs import utils

TEMPLATE = "thinknxg_docs/templates/docs/page.html"
ASSET_VERSION = "1.0.0"


def _js(obj):
    """JSON safe to embed inside a <script> tag."""
    return json.dumps(obj).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _resp(body, status=200, content_type="text/html; charset=utf-8", cache=None):
    r = Response(body, status=status)
    r.headers["Content-Type"] = content_type
    if cache:
        r.headers["Cache-Control"] = cache
    return r


class DocsRenderer(BaseRenderer):
    def can_render(self):
        path = (self.path or "").strip("/")
        if path in ("llms.txt", "docs-sitemap.xml"):
            return frappe.db.table_exists("Docs Space") and bool(utils.get_space_routes())
        first = path.split("/", 1)[0]
        return bool(first) and first in utils.get_space_routes()

    # ------------------------------------------------------------------ main
    def render(self):
        path = (self.path or "").strip("/")
        settings = utils.get_settings()
        if path == "llms.txt":
            return self.root_llms(settings)
        if path == "docs-sitemap.xml":
            return self.sitemap_index()

        space_name, _sep, rest = path.partition("/")
        space = frappe.get_cached_doc("Docs Space", space_name)
        can_edit = frappe.session.user != "Guest" and frappe.has_permission("Docs Page", "write")
        if not cint(space.published) and not can_edit:
            return self.not_found(settings, None, can_edit)

        if rest == "llms.txt" and cint(settings.enable_llms_txt):
            return self.space_llms(space)
        if rest == "sitemap.xml":
            return self.space_sitemap(space)

        tree = utils.get_tree(space.name)
        want_md = rest.lower().endswith(".md") and cint(settings.enable_llms_txt)
        slug = rest[:-3] if want_md else rest
        slug = slug.strip("/").lower()

        if not slug:
            name = space.home_page if space.home_page in tree["ancestors"] else None
            if not name and tree["flat"]:
                name = tree["flat"][0]["name"]
        else:
            name = tree["by_slug"].get(slug)

        if not name:
            return self.not_found(settings, space, can_edit, tree)

        page = frappe.get_doc("Docs Page", name)
        if want_md:
            return self.markdown_source(space, page)
        return self.render_page(settings, space, tree, page, can_edit)

    # ----------------------------------------------------------------- pages
    def base_context(self, settings, space, can_edit, tree=None):
        accent = settings.primary_color or "#0A7C78"
        ctx = frappe._dict(
            settings=settings,
            brand_name=settings.brand_name or "thinkNXG Docs",
            accent=accent,
            space=space,
            spaces=utils.get_switcher_spaces(space.name if space else None, include_unpublished=can_edit),
            tree=(tree or {}).get("tree", []),
            header_links=settings.get("header_links") or [],
            can_edit=can_edit,
            asset_version=ASSET_VERSION,
            year=getdate().year,
            _=_,
        )
        ctx.js_config = {
            "space": space.name if space else None,
            "spaceTitle": space.title if space else None,
            "searchEnabled": cint(settings.enable_search),
            "feedbackEnabled": cint(settings.enable_feedback),
            "csrfToken": frappe.sessions.get_csrf_token() if frappe.session.user != "Guest" else None,
        }
        return ctx

    def render_page(self, settings, space, tree, page, can_edit):
        ctx = self.base_context(settings, space, can_edit, tree)
        body_html, toc = utils.render_markdown(page.name, str(page.modified), page.content)
        flat = tree["flat"]
        idx = next((i for i, p in enumerate(flat) if p["name"] == page.name), None)
        base_url = utils.public_base_url()
        page_url = f"{base_url}/{page.route}"
        md_url = f"/{page.route}.md"
        updated = page.source_updated if page.source_updated and getdate(page.source_updated) > getdate(page.modified) \
            else page.modified
        ai_prompt = f"Read {base_url}{md_url} so I can ask questions about it."
        ctx.update(
            page=page,
            body_html=body_html,
            toc=[t for t in toc if t["level"] in (2, 3)],
            breadcrumbs=tree["ancestors"].get(page.name, []),
            active_name=page.name,
            open_names=tree["open"].get(page.name, []),
            prev=flat[idx - 1] if idx not in (None, 0) else None,
            next=flat[idx + 1] if idx is not None and idx + 1 < len(flat) else None,
            last_updated=pretty_date(updated) if cint(settings.show_last_updated) else None,
            last_updated_iso=str(updated)[:10],
            md_url=md_url if cint(settings.enable_llms_txt) else None,
            edit_url=f"/app/docs-page/{quote(page.name)}" if can_edit else None,
            canonical_url=page_url,
            page_title=f"{page.title} | {space.title}",
            meta_description=page.description or utils.markdown_to_plain(page.content)[:160],
            chatgpt_url="https://chatgpt.com/?hints=search&q=" + quote(ai_prompt),
            claude_url="https://claude.ai/new?q=" + quote(ai_prompt),
            is_404=False,
        )
        ctx.js_config.update({"page": page.name, "mdUrl": ctx.md_url})
        ctx.js_config_json = _js(ctx.js_config)
        self.count_view(settings, page.name)
        html = frappe.render_template(TEMPLATE, ctx)
        return _resp(html, 200)

    def not_found(self, settings, space, can_edit, tree=None):
        if space is None:
            from frappe.website.page_renderers.not_found_page import NotFoundPage

            return NotFoundPage(self.path, 404).render()
        ctx = self.base_context(settings, space, can_edit, tree)
        ctx.update(page=None, body_html="", toc=[], breadcrumbs=[], active_name=None, open_names=[],
                   prev=None, next=None, last_updated=None, md_url=None, edit_url=None,
                   canonical_url=f"{utils.public_base_url()}/{space.name}",
                   page_title=f"{_('Page not found')} | {space.title}", meta_description="", is_404=True)
        ctx.js_config_json = _js(ctx.js_config)
        return _resp(frappe.render_template(TEMPLATE, ctx), 404)

    def count_view(self, settings, name):
        if not cint(settings.enable_page_views):
            return
        try:
            c = utils.cache()
            c.hincrby(c.make_key(utils.VIEWS_KEY), name, 1)
        except Exception:
            pass

    # ------------------------------------------------------- machine output
    def markdown_source(self, space, page):
        url = f"{utils.public_base_url()}/{page.route}"
        updated = str(page.source_updated or page.modified)[:10]
        fm = (
            "---\n"
            f"title: {json.dumps(page.title, ensure_ascii=False)}\n"
            f"space: {json.dumps(space.title, ensure_ascii=False)}\n"
            f"url: {json.dumps(url)}\n"
            f"updated: {json.dumps(updated)}\n"
            "---\n\n"
        )
        return _resp(fm + (page.content or ""), content_type="text/markdown; charset=utf-8",
                     cache="public, max-age=300")

    def space_llms(self, space):
        base = utils.public_base_url()
        tree = utils.get_tree(space.name)
        lines = [f"# {space.title}", "", "Append `.md` to any URL below for that page's raw markdown source.", "",
                 f"## {space.title}", ""]
        descs = dict(frappe.get_all("Docs Page", filters={"space": space.name, "page_type": "Page",
                                                          "description": ("is", "set")},
                                    fields=["name", "description"], as_list=True))

        def walk(nodes, depth):
            pad = "  " * depth
            for n in nodes:
                if n["type"] == "Group":
                    lines.append(f"{pad}- **{n['label']}**")
                elif n["type"] == "Page":
                    d = descs.get(n["name"])
                    lines.append(f"{pad}- [{n['label']}]({base}{n['url']}.md)" + (f": {d}" if d else ""))
                else:
                    u = n["url"] if n.get("external") else f"{base}{n['url']}"
                    lines.append(f"{pad}- [{n['label']}](<{u}>)")
                if n["children"]:
                    walk(n["children"], depth + 1)

        walk(tree["tree"], 0)
        return _resp("\n".join(lines) + "\n", content_type="text/plain; charset=utf-8", cache="public, max-age=300")

    def root_llms(self, settings):
        base = utils.public_base_url()
        lines = [f"# {settings.brand_name or 'thinkNXG Docs'}", "",
                 "Each space below links to its own llms.txt index. Append `.md` to any page URL on this "
                 "site to get that page's raw markdown source.", "", "## Spaces", ""]
        for sp in utils.get_switcher_spaces():
            lines.append(f"- [{sp.title}]({base}/{sp.name}/llms.txt)")
        return _resp("\n".join(lines) + "\n", content_type="text/plain; charset=utf-8", cache="public, max-age=300")

    def space_sitemap(self, space):
        base = utils.public_base_url()
        rows = frappe.get_all("Docs Page", filters={"space": space.name, "page_type": "Page", "published": 1},
                              fields=["route", "modified"], order_by="lft asc", limit_page_length=0)
        out = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        for r in rows:
            out.append(f"<url><loc>{xml_escape(base + '/' + r.route)}</loc>"
                       f"<lastmod>{str(r.modified)[:10]}</lastmod></url>")
        out.append("</urlset>")
        return _resp("\n".join(out), content_type="application/xml; charset=utf-8", cache="public, max-age=3600")

    def sitemap_index(self):
        base = utils.public_base_url()
        out = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        for sp in utils.get_switcher_spaces():
            out.append(f"<sitemap><loc>{xml_escape(f'{base}/{sp.name}/sitemap.xml')}</loc></sitemap>")
        out.append("</sitemapindex>")
        return _resp("\n".join(out), content_type="application/xml; charset=utf-8", cache="public, max-age=3600")
