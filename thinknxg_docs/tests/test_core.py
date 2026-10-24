"""Unit tests for the pure-Python core (no Frappe needed).

Run:  python -m unittest thinknxg_docs.tests.test_core      (from the app repo root)
"""

import unittest

from thinknxg_docs.rebrand import Rebrander
from thinknxg_docs.source_parser import (
    normalize_slug,
    parse_llms_index,
    plan_import,
    split_frontmatter,
    strip_leading_h1,
)

BASE = "https://docs.example.io/erpnext"

INDEX = """# ERPNext

Append `.md` to any URL below for that page's raw markdown source.

## ERPNext

- [Introduction](https://docs.example.io/erpnext/introduction.md)
  - [Introduction](https://docs.example.io/erpnext/introduction.md)
  - [Why ERP?](https://docs.example.io/erpnext/why-ERP.md)
- **Setup**
  - [Company](https://docs.example.io/erpnext/company-setup.md): Set up your company.
  - **Core Settings**
    - [System Settings](https://docs.example.io/erpnext/system-settings.md): Configure things.
  - [Import COA](<https://docs.example.io/erpnext/chart-of-accounts-importer>)
- [Buying](https://docs.example.io/erpnext/buying-overview.md)
  - [Purchase Order](https://docs.example.io/erpnext/purchase-order.md)
  - [Company again](https://docs.example.io/erpnext/company-setup.md)
- [Le Fichier \\[FEC\\]](https://docs.example.io/erpnext/fec.md)
- [Fetch value](https://docs.example.io/erpnext/fetch value in child table.md)
"""


class TestParser(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_slug("Selling-in-different-UOM.md"), "selling-in-different-uom")
        self.assertEqual(normalize_slug("fetch value in child table.md"), "fetch-value-in-child-table")
        self.assertEqual(normalize_slug("data-management/introduction"), "data-management/introduction")

    def test_tree(self):
        roots = parse_llms_index(INDEX)
        self.assertEqual([r.title for r in roots],
                         ["Introduction", "Setup", "Buying", "Le Fichier [FEC]", "Fetch value"])
        self.assertEqual(len(roots[1].children), 3)
        self.assertTrue(roots[1].children[2].angle)
        self.assertEqual(roots[1].children[0].description, "Set up your company.")

    def test_plan(self):
        items = plan_import(parse_llms_index(INDEX), BASE)
        by_key = {i["key"]: i for i in items}
        # group whose url repeats as a child → plain group, one page
        self.assertEqual(by_key["group:introduction"]["type"], "Group")
        self.assertEqual(sum(1 for i in items if i["key"] == "page:introduction"), 1)
        # group with its own unique url → overview page as first child
        self.assertEqual(by_key["page:buying-overview"]["parent"], "group:buying")
        self.assertEqual(by_key["page:buying-overview"]["sort"], 5)
        # duplicate .md → Link
        dup = [i for i in items if i["type"] == "Link" and i.get("target_slug") == "company-setup"]
        self.assertEqual(len(dup), 1)
        # angle reference → Link
        self.assertTrue(any(i.get("target_slug") == "chart-of-accounts-importer" for i in items))
        # parents always appear before children
        seen = set()
        for i in items:
            if i["parent"]:
                self.assertIn(i["parent"], seen)
            seen.add(i["key"])
        self.assertIn("page:fetch-value-in-child-table", by_key)

    def test_frontmatter(self):
        meta, body = split_frontmatter('---\ntitle: "Intro"\nupdated: "2026-04-27"\n---\n\n## Hi\n')
        self.assertEqual(meta["title"], "Intro")
        self.assertEqual(meta["updated"], "2026-04-27")
        self.assertEqual(body, "## Hi\n")
        self.assertEqual(strip_leading_h1("# Intro\n\ntext", "Intro"), "text")


class TestRebrand(unittest.TestCase):
    def setUp(self):
        self.r = Rebrander(space_maps=[("https://docs.frappe.io/erpnext", "/thinknxgerp"),
                                       ("https://docs.frappe.io/hr", "/thinknxghr")],
                           url_rules=[("https://discuss.frappe.io", "https://community.thinknxg.com")])

    def test_text(self):
        t = self.r.text
        self.assertEqual(t("ERPNext is built on the Frappe Framework."),
                         "thinkNXG ERP is built on the thinkNXG Framework.")
        self.assertEqual(t("Use Frappe HR with Frappe Cloud."), "Use thinkNXG HR with thinkNXG Cloud.")
        self.assertEqual(t("ERPNext's ledger"), "thinkNXG ERP's ledger")
        self.assertEqual(t("frappe.get_doc"), "frappe.get_doc")  # lowercase identifier untouched
        self.assertEqual(t("ERPNextX"), "ERPNextX")  # not a whole word
        self.assertEqual(t(t("ERPNext")), "thinkNXG ERP")  # idempotent

    def test_markdown(self):
        md = (
            "## What is ERPNext?\n\n"
            "See [Sales Invoice](https://docs.frappe.io/erpnext/sales-invoice.md) and "
            "[HR](<https://docs.frappe.io/hr/leave>) or https://docs.frappe.io/erpnext/Selling-in-different-UOM.\n\n"
            "![ERPNext](/files/hero.png)\n\n"
            "Run `bench get-app erpnext` in Frappe:\n\n"
            "```bash\nbench --site x install-app erpnext  # Frappe ERPNext\n```\n\n"
            "Visit <https://discuss.frappe.io/c/erpnext> or https://frappe.io.\n\n"
            '<img src="https://docs.frappe.io/erpnext/x" alt="ERPNext screen">\n'
        )
        out = self.r.markdown(md)
        self.assertIn("## What is thinkNXG ERP?", out)
        self.assertIn("[Sales Invoice](/thinknxgerp/sales-invoice)", out)
        self.assertIn("[HR](</thinknxghr/leave>)", out)
        self.assertIn("/thinknxgerp/selling-in-different-uom.", out)
        self.assertIn("![thinkNXG ERP](/files/hero.png)", out)
        self.assertIn("`bench get-app erpnext` in thinkNXG:", out)
        self.assertIn("```bash\nbench --site x install-app erpnext  # Frappe ERPNext\n```", out)
        self.assertIn("<https://community.thinknxg.com/c/erpnext>", out)
        self.assertIn("https://frappe.io.", out)  # unmapped URL left intact
        self.assertIn('src="/thinknxgerp/x" alt="thinkNXG ERP screen"', out)

    def test_related_topics_relative_links(self):
        # verbatim shape of upstream "Related topics" sections
        md = (
            "## Related topics\n\n"
            "- [Sales Order](/erpnext/sales-order)\n"
            "- [Credit Note and Sales Return](/erpnext/sales-return)\n"
            "- [Payment Ledger](</erpnext/user/manual/en/payment_ledger>)\n"
            "- [Leave Application](/hr/leave-application#approval)\n"
            "- [CRM Lead](/crm/lead)\n"
            "- [Already ours](/thinknxgerp/journal-entry)\n"
            "- [Selling in UOM](//docs.frappe.io/erpnext/Selling-in-different-UOM)\n\n"
            "![shot](/files/si.png) and <a href=\"/erpnext/customer\">Customer</a>\n"
        )
        r = Rebrander(space_maps=[("https://docs.frappe.io/erpnext", "/thinknxgerp"),
                                  ("https://docs.frappe.io/hr", "/thinknxghr")],
                      slug_resolver=lambda t, s: {"user/manual/en/payment_ledger": "payment_ledger"}.get(s),
                      relative_origin="https://docs.frappe.io", own_routes={"thinknxgerp", "thinknxghr"})
        out = r.markdown(md)
        self.assertIn("[Sales Order](/thinknxgerp/sales-order)", out)
        self.assertIn("[Credit Note and Sales Return](/thinknxgerp/sales-return)", out)
        self.assertIn("[Payment Ledger](</thinknxgerp/payment_ledger>)", out)
        self.assertIn("[Leave Application](/thinknxghr/leave-application#approval)", out)
        self.assertIn("[CRM Lead](https://docs.frappe.io/crm/lead)", out)  # not hosted → absolute, still works
        self.assertIn("[Already ours](/thinknxgerp/journal-entry)", out)
        self.assertIn("[Selling in UOM](/thinknxgerp/selling-in-different-uom)", out)
        self.assertIn("![shot](/files/si.png)", out)
        self.assertIn('<a href="/thinknxgerp/customer">Customer</a>', out)
        self.assertNotIn("](/erpnext", out)
        # without relative_origin (hand-typed pages) unknown site paths are left alone
        plain = Rebrander(space_maps=[("https://docs.frappe.io/erpnext", "/thinknxgerp")])
        self.assertEqual(plain.url("/contact"), "/contact")
        self.assertEqual(plain.url("/erpnext/sales-order"), "/thinknxgerp/sales-order")
        self.assertEqual(plain.url("/erpnext-blog/x"), "/erpnext-blog/x")

    def test_anchor_and_resolver(self):
        r = Rebrander(space_maps=[("https://docs.frappe.io/erpnext", "/thinknxgerp")],
                      slug_resolver=lambda target, slug: {"old/page": "page"}.get(slug))
        self.assertEqual(r.url("https://docs.frappe.io/erpnext/old/page.md#setup"), "/thinknxgerp/page#setup")
        self.assertEqual(r.url("https://docs.frappe.io/erpnext"), "/thinknxgerp")
        self.assertEqual(r.url("https://docs.frappe.io/erpnextfoo"), "https://docs.frappe.io/erpnextfoo")


if __name__ == "__main__":
    unittest.main()
