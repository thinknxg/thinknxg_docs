"""Scheduled jobs."""

import frappe

from thinknxg_docs import utils


def flush_page_views():
    """Move page-view counters from Redis into Docs Page.views (hourly)."""
    try:
        c = utils.cache()
        key = c.make_key(utils.VIEWS_KEY)
        tmp = key + ":flush"
        if not c.exists(key):
            return
        c.rename(key, tmp)
        data = c.hgetall(tmp)
        c.delete(tmp)
    except Exception:
        frappe.log_error(title="thinkNXG Docs: page view flush failed")
        return
    for name, count in (data or {}).items():
        name = name.decode() if isinstance(name, bytes) else name
        try:
            count = int(count)
        except (TypeError, ValueError):
            continue
        if count and frappe.db.exists("Docs Page", name):
            frappe.db.sql(
                "update `tabDocs Page` set views = coalesce(views, 0) + %s where name = %s", (count, name))
    frappe.db.commit()
