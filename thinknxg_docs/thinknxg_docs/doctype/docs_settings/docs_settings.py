import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from thinknxg_docs import utils


class DocsSettings(Document):
    def validate(self):
        if self.docs_base_url:
            self.docs_base_url = self.docs_base_url.strip().rstrip("/")
        for row in self.get("rebrand_rules") or []:
            if row.rule_type == "Text" and row.find_text and row.find_text == row.replace_with:
                frappe.throw(_("Row {0}: Find and Replace With are the same").format(row.idx))
        if cint(self.use_as_home_page) and not self.default_space:
            frappe.throw(_("Set a Default Space to use it as the site home page"))

    def on_update(self):
        frappe.local.thinknxg_docs_rebrander = None
        utils.clear_cache()
        if cint(self.use_as_home_page) and self.default_space:
            ws = frappe.get_single("Website Settings")
            if ws.home_page != self.default_space:
                ws.home_page = self.default_space
                ws.flags.ignore_permissions = True
                ws.save()
