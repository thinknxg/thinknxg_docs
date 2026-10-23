import re

import frappe
from frappe import _
from frappe.model.document import Document

from thinknxg_docs import utils


class DocsSpace(Document):
    def validate(self):
        route = (self.route or "").strip().strip("/").lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", route or ""):
            frappe.throw(_("Route may contain only lowercase letters, digits, '-' and '_'"))
        if route in utils.RESERVED_ROUTES:
            frappe.throw(_("Route {0} is reserved by the site").format(frappe.bold(route)))
        self.route = route

        if self.source_base_url:
            self.source_base_url = self.source_base_url.strip().rstrip("/")
            if self.source_base_url.endswith("/llms.txt"):
                self.source_base_url = self.source_base_url[: -len("/llms.txt")]
            if not self.source_llms_url:
                self.source_llms_url = self.source_base_url + "/llms.txt"

        if self.home_page and not self.is_new():
            row = frappe.db.get_value("Docs Page", self.home_page, ["space", "page_type"], as_dict=True)
            if not row or row.space != self.name or row.page_type != "Page":
                frappe.throw(_("Home Page must be a Page in this Space"))

    def on_update(self):
        utils.clear_cache()

    def on_trash(self):
        if frappe.db.count("Docs Page", {"space": self.name}):
            frappe.throw(_("Delete or move the pages of this Space first"))

    def after_delete(self):
        utils.clear_cache()

    def after_rename(self, old, new, merge=False):
        frappe.db.set_value("Docs Space", new, "route", new, update_modified=False)
        frappe.db.sql(
            "update `tabDocs Page` set route = concat(%s, '/', slug) where space = %s and page_type = 'Page'",
            (new, new),
        )
        utils.clear_cache()
