"""Import + rebrand an upstream documentation space (llms.txt index + per-page .md source).

Flow
  1. Fetch <source>/llms.txt and turn the nested list into Groups / Pages / Links.
  2. For each Page fetch <page>.md, strip front matter, localise images, keep the original
     markdown in ``source_content`` and store the rebranded version in ``content``.
  3. Resolve Link items to the imported pages, optionally unpublish pages no longer upstream.

Re-running is idempotent: items are matched on ``import_key``; pages with
"Lock From Re-import" keep their content.
"""

import os
import re
import time
from urllib.parse import urljoin, urlsplit

import frappe
from frappe.utils import cint, flt, getdate, now_datetime
from requests.utils import requote_uri

from thinknxg_docs import utils
from thinknxg_docs.rebrand import Rebrander
from thinknxg_docs.source_parser import (
    parse_llms_index,
    plan_import,
    split_frontmatter,
    strip_leading_h1,
)

MAX_IMAGE_BYTES = 15 * 1024 * 1024
_IMG_MD_RE = re.compile(r"(!\[[^\]]*\]\()(<[^>]+>|[^)\s]+)((?:\s+\"[^\"]*\")?\))")
_IMG_HTML_RE = re.compile(r"(<img\b[^>]*?\bsrc\s*=\s*)([\"'])(.*?)\2", re.I)


# ----------------------------------------------------------------- public API
def create_log(space, limit=0, prune=0):
    sp = frappe.get_doc("Docs Space", space)
    if not sp.source_llms_url:
        frappe.throw(frappe._("Set 'Source Index (llms.txt)' on Space {0} first").format(space))
    log = frappe.get_doc({
        "doctype": "Docs Import Log",
        "space": space,
        "status": "Queued",
        "source_url": sp.source_llms_url,
        "options": f"limit={cint(limit)} prune={cint(prune)}",
    })
    log.insert(ignore_permissions=True)
    return log.name


def enqueue_import(space, limit=0, prune=0):
    log_name = create_log(space, limit, prune)
    frappe.enqueue(
        "thinknxg_docs.importer.run_import",
        queue="long",
        timeout=4 * 3600,
        enqueue_after_commit=True,
        log_name=log_name,
        limit=cint(limit),
        prune=cint(prune),
        notify_user=frappe.session.user,
    )
    return log_name


def run_import(log_name, limit=0, prune=0, notify_user=None, verbose=False):
    job = ImportJob(log_name, limit=cint(limit), prune=cint(prune), notify_user=notify_user, verbose=verbose)
    return job.run()


# ------------------------------------------------------------------- the job
class ImportJob:
    def __init__(self, log_name, limit=0, prune=0, notify_user=None, verbose=False):
        self.log = frappe.get_doc("Docs Import Log", log_name)
        self.space = frappe.get_doc("Docs Space", self.log.space)
        self.settings = utils.get_settings()
        self.limit, self.prune, self.verbose = limit, prune, verbose
        self.notify_user = notify_user
        self.lines = []
        self.counts = dict(created=0, updated=0, skipped=0, failed=0, images=0)
        self.key_to_name = {}
        self.touched = set()
        self.image_cache = {}
        base = (self.space.source_base_url or "").rstrip("/")
        if not base:
            base = self.space.source_llms_url.rsplit("/", 1)[0]
        self.base = base
        parts = urlsplit(base)
        self.origin = f"{parts.scheme}://{parts.netloc}"
        self.session = None

    # ------------------------------------------------------------- helpers
    def say(self, msg):
        line = f"[{now_datetime().strftime('%H:%M:%S')}] {msg}"
        self.lines.append(line)
        if self.verbose:
            print(line)

    def http(self):
        if self.session is None:
            import requests

            self.session = requests.Session()
            self.session.headers["User-Agent"] = self.settings.user_agent or "thinkNXG-Docs-Importer/1.0"
        return self.session

    def get(self, url, binary=False):
        timeout = cint(self.settings.request_timeout) or 30
        last = None
        for attempt in range(3):
            try:
                resp = self.http().get(requote_uri(url), timeout=timeout)
                if resp.status_code == 404:
                    raise FileNotFoundError(url)
                resp.raise_for_status()
                if binary:
                    if len(resp.content) > MAX_IMAGE_BYTES:
                        raise ValueError("image too large")
                    return resp.content
                resp.encoding = resp.encoding or "utf-8"
                return resp.text
            except FileNotFoundError:
                raise
            except Exception as e:  # network hiccup → retry
                last = e
                time.sleep(1.5 * (attempt + 1))
        raise last

    def save_log(self, status=None, final=False):
        vals = {
            "created_count": self.counts["created"],
            "updated_count": self.counts["updated"],
            "skipped_count": self.counts["skipped"],
            "failed_count": self.counts["failed"],
            "images_count": self.counts["images"],
            "log": "\n".join(self.lines)[-200000:],
        }
        if status:
            vals["status"] = status
        if final:
            vals["finished_at"] = now_datetime()
        frappe.db.set_value("Docs Import Log", self.log.name, vals, update_modified=True)
        frappe.db.commit()

    def progress(self, done, total, title):
        if not self.notify_user:
            return
        frappe.publish_realtime(
            "thinknxg_docs_import_progress",
            {"space": self.space.name, "done": done, "total": total, "title": title, "log": self.log.name},
            user=self.notify_user,
        )

    # -------------------------------------------------------------- images
    def localise_images(self, body):
        mode = self.settings.image_mode or "Download to this site"

        def target(u):
            raw = u.strip()
            if raw.startswith("<") and raw.endswith(">"):
                raw = raw[1:-1]
            if raw.startswith("/files/") or raw.startswith("/private/files/"):
                absolute = self.origin + raw
            elif raw.startswith(self.origin + "/files/"):
                absolute = raw
            elif raw.startswith("http") or raw.startswith("data:") or raw.startswith("//"):
                return u
            else:
                absolute = urljoin(self.base + "/", raw)
            if mode != "Download to this site":
                return absolute
            if absolute in self.image_cache:
                return self.image_cache[absolute]
            local = self.download_image(absolute)
            self.image_cache[absolute] = local or absolute
            return self.image_cache[absolute]

        body = _IMG_MD_RE.sub(lambda m: m.group(1) + target(m.group(2)) + m.group(3), body)
        body = _IMG_HTML_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{target(m.group(3))}{m.group(2)}", body)
        return body

    def download_image(self, url):
        fname = os.path.basename(urlsplit(url).path) or "image"
        fname = re.sub(r"[^A-Za-z0-9._-]+", "-", fname)[-120:]
        fname = f"tnxg-docs-{fname}"
        existing = frappe.db.get_value("File", {"file_name": fname, "is_private": 0}, "file_url")
        if existing:
            return existing
        try:
            data = self.get(url, binary=True)
            f = frappe.get_doc({
                "doctype": "File",
                "file_name": fname,
                "content": data,
                "is_private": 0,
                "attached_to_doctype": "Docs Space",
                "attached_to_name": self.space.name,
            })
            f.flags.ignore_permissions = True
            f.insert()
            self.counts["images"] += 1
            return f.file_url
        except Exception as e:
            self.say(f"  image kept remote ({e.__class__.__name__}): {url}")
            return None

    # ---------------------------------------------------------------- upsert
    def find_existing(self, item):
        name = frappe.db.get_value("Docs Page", {"space": self.space.name, "import_key": item["key"]}, "name")
        if not name and item["type"] == "Page":
            name = frappe.db.get_value(
                "Docs Page", {"space": self.space.name, "slug": item["slug"], "page_type": "Page"}, "name")
        return name

    def upsert(self, item, rb):
        parent = self.key_to_name.get(item["parent"]) if item["parent"] else None
        name = self.find_existing(item)
        doc = frappe.get_doc("Docs Page", name) if name else frappe.new_doc("Docs Page")
        is_new = not name

        doc.space = self.space.name
        doc.page_type = item["type"]
        doc.parent_docs_page = parent
        doc.sort_order = item["sort"]
        doc.import_key = item["key"]
        if is_new:
            doc.published = 1

        locked = not is_new and cint(doc.lock_from_import)
        label = rb.text(item["title"])

        if item["type"] == "Page":
            doc.slug = item["slug"]
            if locked:
                self.counts["skipped"] += 1
            else:
                fetch_url = item["fetch_url"]
                if not fetch_url.startswith("http"):
                    fetch_url = urljoin(self.base + "/", fetch_url)
                if not fetch_url.lower().endswith(".md"):
                    fetch_url += ".md"
                raw = self.get(fetch_url)
                meta, body = split_frontmatter(raw)
                src_title = meta.get("title") or item["title"]
                body = strip_leading_h1(body, src_title)
                body = self.localise_images(body)
                doc.source_url = fetch_url[:-3] if fetch_url.lower().endswith(".md") else fetch_url
                doc.source_title = src_title
                doc.source_content = body
                doc.title = rb.text(src_title)
                doc.sidebar_label = label if label != doc.title else None
                doc.description = rb.text(item.get("description") or meta.get("description") or "") or None
                doc.content = rb.markdown(body)
                if meta.get("updated"):
                    try:
                        doc.source_updated = getdate(meta["updated"])
                    except Exception:
                        pass
        else:
            if not locked:
                doc.title = label
                doc.sidebar_label = None
                doc.description = rb.text(item.get("description") or "") or None
            if item["type"] == "Link":
                doc.link_to_page = None
                doc.external_url = rb.url(item["external_url"]) if item.get("external_url") else None

        doc.flags.ignore_permissions = True
        doc.save()
        if is_new:
            self.counts["created"] += 1
        elif not (locked and item["type"] == "Page"):
            self.counts["updated"] += 1
        self.key_to_name[item["key"]] = doc.name
        self.touched.add(doc.name)
        return doc

    def resolve_links(self, plan):
        resolver = utils.make_slug_resolver()
        for item in plan:
            if item["type"] != "Link" or not item.get("target_slug"):
                continue
            name = self.key_to_name.get(item["key"])
            if not name:
                continue
            slug = resolver(self.space.name, item["target_slug"])
            target = frappe.db.get_value(
                "Docs Page", {"space": self.space.name, "slug": slug, "page_type": "Page"}, "name")
            if target:
                frappe.db.set_value("Docs Page", name, {"link_to_page": target, "published": 1})
            else:
                frappe.db.set_value("Docs Page", name, "published", 0)
                self.say(f"  unresolved link hidden: {item['title']} → {item['target_slug']}")

    def prune_missing(self):
        stale = frappe.get_all(
            "Docs Page",
            filters={"space": self.space.name, "import_key": ("is", "set"), "published": 1,
                     "lock_from_import": 0, "name": ("not in", list(self.touched) or ["-"])},
            pluck="name",
        )
        for name in stale:
            frappe.db.set_value("Docs Page", name, "published", 0)
        if stale:
            self.say(f"Unpublished {len(stale)} item(s) no longer in the source index")

    # ------------------------------------------------------------------- run
    def run(self):
        frappe.flags.thinknxg_docs_importing = True
        try:
            frappe.db.set_value("Docs Import Log", self.log.name,
                                {"status": "Running", "started_at": now_datetime()})
            frappe.db.commit()
            self.say(f"Fetching index {self.space.source_llms_url}")
            index = self.get(self.space.source_llms_url)
            plan = plan_import(parse_llms_index(index), self.base)
            if not plan:
                raise ValueError("The index contained no entries")
            if self.limit:
                pages_seen, trimmed = 0, []
                for it in plan:
                    if it["type"] == "Page":
                        pages_seen += 1
                        if pages_seen > self.limit:
                            continue
                    trimmed.append(it)
                plan = trimmed
            total = len(plan)
            frappe.db.set_value("Docs Import Log", self.log.name, "total_items", total)
            planned_slugs = [i["slug"] for i in plan if i["type"] == "Page"]
            rb = _for_imported(utils.get_rebrander(), self.base,
                               utils.make_slug_resolver({self.space.name: planned_slugs}))
            self.say(f"{total} items ({len(planned_slugs)} pages) planned")

            delay = flt(self.settings.import_delay)
            for i, item in enumerate(plan, 1):
                try:
                    self.upsert(item, rb)
                    frappe.db.commit()  # one item per transaction: a failure never undoes earlier items
                except Exception as e:
                    frappe.db.rollback()
                    self.counts["failed"] += 1
                    self.say(f"  FAILED {item['type']} '{item['title']}': {e.__class__.__name__}: {e}"[:500])
                if item["type"] == "Page" and delay:
                    time.sleep(delay)
                if i % 10 == 0 or i == total:
                    self.progress(i, total, item["title"])
                    self.save_log()

            self.resolve_links(plan)
            if self.prune and not self.limit:
                self.prune_missing()

            if not self.space.home_page or not frappe.db.exists("Docs Page", self.space.home_page):
                home = frappe.db.get_value("Docs Page", {"space": self.space.name, "slug": "introduction",
                                                         "page_type": "Page"}, "name")
                if not home:
                    home = frappe.db.get_value("Docs Page", {"space": self.space.name, "page_type": "Page",
                                                             "published": 1}, "name", order_by="lft asc")
                if home:
                    frappe.db.set_value("Docs Space", self.space.name, "home_page", home)
            frappe.db.set_value("Docs Space", self.space.name,
                                {"last_import": now_datetime(), "last_import_log": self.log.name})
            utils.clear_cache(self.space.name)
            status = "Completed with Errors" if self.counts["failed"] else "Completed"
            self.say(f"Done: {self.counts}")
            self.save_log(status, final=True)
            self.progress(total, total, "Done")
            return self.counts
        except Exception as e:
            frappe.db.rollback()
            self.say(f"Import failed: {e.__class__.__name__}: {e}")
            frappe.log_error(title=f"thinkNXG Docs import failed ({self.space.name})")
            self.save_log("Failed", final=True)
            raise
        finally:
            frappe.flags.thinknxg_docs_importing = False


def _clone_with_resolver(rb, resolver):
    """Shallow copy of a Rebrander with a different slug resolver."""
    clone = Rebrander.__new__(Rebrander)
    clone.__dict__.update(rb.__dict__)
    clone.slug_resolver = resolver
    return clone


def _source_origin(base_url):
    parts = urlsplit(base_url or "")
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else None


def _for_imported(rb, base_url, resolver=None):
    """Rebrander for imported text: site-relative links (/erpnext/x) into spaces we host are
    mapped to our routes; links into upstream spaces we don't host become absolute."""
    clone = _clone_with_resolver(rb, resolver or rb.slug_resolver)
    clone.relative_origin = _source_origin(base_url)
    clone.own_routes = set(utils.get_space_routes(refresh=True))
    return clone


# ------------------------------------------------------------ re-branding job
def reapply_branding(space=None):
    """Regenerate content from the stored originals using the current rules."""
    frappe.local.thinknxg_docs_rebrander = None
    rb = utils.get_rebrander()
    filters = {"page_type": ("!=", "Link")}
    if space:
        filters["space"] = space
    rows = frappe.get_all("Docs Page", filters=filters,
                          fields=["name", "title", "sidebar_label", "description", "content", "source_content",
                                  "source_title", "skip_rebrand", "lock_from_import", "space"],
                          limit_page_length=0)
    bases = dict(frappe.get_all("Docs Space", fields=["name", "source_base_url"], as_list=True))
    imported_rb = {}
    changed = 0
    for r in rows:
        if cint(r.skip_rebrand):
            continue
        prb = rb
        if r.source_content and bases.get(r.space):
            if r.space not in imported_rb:
                imported_rb[r.space] = _for_imported(rb, bases[r.space])
            prb = imported_rb[r.space]
        vals = {}
        if r.source_content and not cint(r.lock_from_import):
            vals["content"] = prb.markdown(r.source_content)
            vals["title"] = rb.text(r.source_title or r.title)
        else:
            vals["content"] = prb.markdown(r.content or "")
            vals["title"] = rb.text(r.title)
        if r.sidebar_label:
            vals["sidebar_label"] = rb.text(r.sidebar_label)
        if r.description:
            vals["description"] = rb.text(r.description)
        if any((vals.get(k) or "") != (r.get(k) or "") for k in vals):
            frappe.db.set_value("Docs Page", r.name, vals)
            changed += 1
    utils.clear_cache(space)
    frappe.db.commit()
    return changed
