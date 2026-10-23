import frappe
from frappe import _
from frappe.utils.nestedset import NestedSet

from thinknxg_docs import utils
from thinknxg_docs.source_parser import normalize_slug


class DocsPage(NestedSet):
    nsm_parent_field = "parent_docs_page"

    def validate(self):
        if self.parent_docs_page and not frappe.db.exists("Docs Page", self.parent_docs_page):
            if self.parent_docs_page == utils.ROOT_LABEL:
                self.parent_docs_page = None
            else:
                frappe.throw(_("Parent Group {0} does not exist").format(self.parent_docs_page))
        if not self.space and self.parent_docs_page:
            self.space = frappe.db.get_value("Docs Page", self.parent_docs_page, "space")
        if not self.space:
            frappe.throw(_("Space is required"))

        self.page_type = self.page_type or "Page"
        self.is_group = 1 if self.page_type == "Group" else 0
        self.validate_parent()

        if self.page_type == "Page":
            self.set_slug_and_route()
        else:
            self.slug = None
            self.route = None
        if self.page_type == "Link":
            self.validate_link()
        else:
            self.link_to_page = None
            self.external_url = None

        if (not frappe.flags.thinknxg_docs_importing and not self.skip_rebrand
                and utils.rebrand_on_save_enabled()):
            self.apply_rebrand()

    def validate_parent(self):
        if not self.parent_docs_page:
            return
        if self.parent_docs_page == self.name:
            frappe.throw(_("A page cannot be its own parent"))
        parent = frappe.db.get_value("Docs Page", self.parent_docs_page, ["space", "page_type"], as_dict=True)
        if parent.page_type != "Group":
            frappe.throw(_("Parent {0} must be a Group").format(frappe.bold(self.parent_docs_page)))
        if parent.space != self.space:
            frappe.throw(_("Parent Group belongs to a different Space"))

    def set_slug_and_route(self):
        slug = normalize_slug(self.slug or self.title)
        if not slug:
            frappe.throw(_("Slug is required"))
        dup = frappe.db.get_value(
            "Docs Page",
            {"space": self.space, "slug": slug, "page_type": "Page", "name": ("!=", self.name or "")},
            "name",
        )
        if dup:
            frappe.throw(_("Slug {0} is already used by {1} in this Space").format(
                frappe.bold(slug), frappe.get_desk_link("Docs Page", dup)))
        self.slug = slug
        self.route = f"{self.space}/{slug}"

    def validate_link(self):
        if not self.link_to_page and not self.external_url:
            frappe.throw(_("Set either Link To Page or External URL"))
        if self.link_to_page:
            if self.link_to_page == self.name:
                frappe.throw(_("A link cannot point to itself"))
            if frappe.db.get_value("Docs Page", self.link_to_page, "page_type") != "Page":
                frappe.throw(_("Link To Page must be a Page"))

    def apply_rebrand(self):
        rb = utils.get_rebrander()
        self.title = rb.text(self.title)
        if self.sidebar_label:
            self.sidebar_label = rb.text(self.sidebar_label)
        if self.description:
            self.description = rb.text(self.description)
        if self.content:
            self.content = rb.markdown(self.content)

    def on_update(self):
        super().on_update()
        before = self.get_doc_before_save()
        utils.clear_cache(self.space)
        if before and before.space and before.space != self.space:
            utils.clear_cache(before.space)

    def on_trash(self):
        super().on_trash(allow_root_deletion=True)
        frappe.db.delete("Docs Feedback", {"page": self.name})
        for name in frappe.get_all("Docs Page", filters={"link_to_page": self.name}, pluck="name"):
            frappe.db.set_value("Docs Page", name, {"link_to_page": None, "published": 0})
        for sp in frappe.get_all("Docs Space", filters={"home_page": self.name}, pluck="name"):
            frappe.db.set_value("Docs Space", sp, "home_page", None)

    def after_delete(self):
        utils.clear_cache(self.space)
