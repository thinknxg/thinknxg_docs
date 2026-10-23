"""Whitelisted endpoints: public search + feedback, desk actions (import, rebrand, tree view)."""

import html as html_lib
import re

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint

from thinknxg_docs import utils

MANAGER_ROLES = ("Docs Manager", "System Manager")


# ---------------------------------------------------------------- public API
@frappe.whitelist(allow_guest=True)
def search(query=None, space=None, limit=20):
    """Search published pages. All words must match title, description or content."""
    query = re.sub(r"\s+", " ", (query or "")).strip()[:100]
    if len(query) < 2:
        return []
    limit = min(cint(limit) or 20, 50)
    words = [w for w in query.split(" ") if w][:6]

    DP = frappe.qb.DocType("Docs Page")
    DS = frappe.qb.DocType("Docs Space")
    q = (
        frappe.qb.from_(DP)
        .join(DS).on(DS.name == DP.space)
        .select(DP.name, DP.title, DP.route, DP.description, DP.content, DP.space, DS.title.as_("space_title"))
        .where((DP.published == 1) & (DP.page_type == "Page") & (DS.published == 1))
        .limit(200)
    )
    if space:
        q = q.where(DP.space == space)
    for w in words:
        like = f"%{w}%"
        q = q.where(DP.title.like(like) | DP.description.like(like) | DP.content.like(like))
    rows = q.run(as_dict=True)

    ql = query.lower()
    scored = []
    for r in rows:
        title = (r.title or "").lower()
        score = 0
        if title == ql:
            score += 100
        if title.startswith(ql):
            score += 40
        if ql in title:
            score += 25
        score += sum(8 for w in words if w.lower() in title)
        score += sum(3 for w in words if w.lower() in (r.description or "").lower())
        scored.append((score, r))
    scored.sort(key=lambda x: (-x[0], len(x[1].title or "")))

    out = []
    for _score, r in scored[:limit]:
        tree = utils.get_tree(r.space)
        out.append({
            "title": r.title,
            "url": "/" + (r.route or ""),
            "space": r.space_title,
            "breadcrumb": " › ".join(tree["ancestors"].get(r.name, [])),
            "snippet": _snippet(r.description or "", r.content or "", words),
        })
    return out


def _snippet(description, content, words, width=90):
    text = utils.markdown_to_plain(content)
    low = text.lower()
    pos = -1
    for w in words:
        pos = low.find(w.lower())
        if pos >= 0:
            break
    if pos < 0:
        text = description or text
        pos = 0
    start = max(0, pos - width // 2)
    piece = text[start:start + width * 2]
    if start > 0:
        piece = "…" + piece
    if start + width * 2 < len(text):
        piece += "…"
    piece = html_lib.escape(piece)
    for w in sorted(set(words), key=len, reverse=True):
        piece = re.sub(f"({re.escape(html_lib.escape(w))})", r"<mark>\1</mark>", piece, flags=re.I)
    return piece


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=3600)
def submit_feedback(page, helpful, comment=None):
    if not cint(utils.get_settings().enable_feedback):
        frappe.throw(_("Feedback is disabled"))
    row = frappe.db.get_value("Docs Page", {"name": page, "published": 1, "page_type": "Page"},
                              ["name", "space"], as_dict=True)
    if not row:
        frappe.throw(_("Page not found"), frappe.DoesNotExistError)
    helpful = "Yes" if str(helpful).lower() in ("1", "yes", "true") else "No"
    frappe.get_doc({
        "doctype": "Docs Feedback",
        "page": row.name,
        "space": row.space,
        "helpful": helpful,
        "comment": (comment or "").strip()[:2000] or None,
        "user": frappe.session.user,
    }).insert(ignore_permissions=True)
    field = "helpful_count" if helpful == "Yes" else "not_helpful_count"
    frappe.db.sql(
        f"update `tabDocs Page` set `{field}` = coalesce(`{field}`, 0) + 1 where name = %s", row.name)
    return {"ok": True}


# ----------------------------------------------------------------- desk API
@frappe.whitelist()
def start_import(space, limit=0, prune=0):
    frappe.only_for(MANAGER_ROLES)
    from thinknxg_docs.importer import enqueue_import

    return enqueue_import(space, limit=cint(limit), prune=cint(prune))


@frappe.whitelist()
def reapply_branding(space=None):
    frappe.only_for(MANAGER_ROLES)
    frappe.enqueue("thinknxg_docs.importer.reapply_branding", queue="long", timeout=3600,
                   space=space or None, enqueue_after_commit=True)
    return True


@frappe.whitelist()
def clear_docs_cache(space=None):
    frappe.only_for(MANAGER_ROLES)
    utils.clear_cache(space or None)
    return True


@frappe.whitelist()
def get_tree_children(doctype=None, parent=None, space=None, is_root=False, **kwargs):
    """Tree view children for Docs Page, filtered by Space."""
    filters = [["Docs Page", "docstatus", "<", 2]]
    if space:
        filters.append(["Docs Page", "space", "=", space])
    if cint(is_root) or str(is_root).lower() == "true" or not parent or parent == utils.ROOT_LABEL:
        filters.append(["Docs Page", "parent_docs_page", "is", "not set"])
    else:
        filters.append(["Docs Page", "parent_docs_page", "=", parent])
    rows = frappe.get_list(
        "Docs Page",
        filters=filters,
        fields=["name as value", "title", "sidebar_label", "is_group as expandable", "page_type", "published",
                "route", "space"],
        order_by="sort_order asc, lft asc",
        limit_page_length=0,
    )
    for r in rows:
        label = r.sidebar_label or r.title
        if r.page_type == "Link":
            label = "↪ " + label
        if not cint(r.published):
            label += " (hidden)"
        r.title = label
    return rows
