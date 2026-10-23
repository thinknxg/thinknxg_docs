"""Install / migrate hooks: roles, default spaces, default rebranding rules."""

import frappe

from thinknxg_docs.rebrand import DEFAULT_SPACES, DEFAULT_TEXT_RULES

ROLES = ("Docs Manager", "Docs Editor")

WELCOME = """Welcome to the **thinkNXG ERP** documentation.

This page is a placeholder. A *Docs Manager* can import and rebrand the full
documentation from **Docs Space → thinknxgerp → Import from Source**, or run:

```bash
bench --site docs.thinknxg.com thinknxg-docs-import thinknxgerp
```

After the import this page is replaced by the imported *Introduction* page.
"""


def before_install():
    ensure_roles()


def after_install():
    ensure_roles()
    ensure_settings(initial=True)
    ensure_spaces()
    frappe.db.commit()


def after_migrate():
    ensure_roles()
    ensure_settings()


def ensure_roles():
    for role in ROLES:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)


def ensure_settings(initial=False):
    s = frappe.get_single("Docs Settings")
    changed = False
    if not s.get("rebrand_rules"):
        for find, repl, case, word in DEFAULT_TEXT_RULES:
            s.append("rebrand_rules", {"enabled": 1, "rule_type": "Text", "find_text": find,
                                       "replace_with": repl, "match_case": case, "whole_word": word})
        changed = True
    if initial and not s.get("header_links"):
        s.append("header_links", {"label": "Website", "url": "https://thinknxg.com", "open_in_new_tab": 1})
        changed = True
    if not s.brand_name:
        s.brand_name, changed = "thinkNXG Docs", True
    if not s.docs_base_url:
        s.docs_base_url, changed = "https://docs.thinknxg.com", True
    if changed:
        s.flags.ignore_permissions = True
        s.save()


def ensure_spaces():
    if frappe.db.count("Docs Space"):
        return
    for i, (route, title, base, published) in enumerate(DEFAULT_SPACES, 1):
        frappe.get_doc({
            "doctype": "Docs Space",
            "route": route,
            "title": title,
            "published": published,
            "show_in_switcher": 1,
            "sort_order": i,
            "source_base_url": base,
            "source_llms_url": base + "/llms.txt",
            "description": f"{title} documentation",
        }).insert(ignore_permissions=True)

    page = frappe.get_doc({
        "doctype": "Docs Page",
        "space": "thinknxgerp",
        "page_type": "Page",
        "title": "Introduction",
        "slug": "introduction",
        "published": 1,
        "content": WELCOME,
        "skip_rebrand": 1,
    }).insert(ignore_permissions=True)
    frappe.db.set_value("Docs Space", "thinknxgerp", "home_page", page.name)

    s = frappe.get_single("Docs Settings")
    s.default_space = "thinknxgerp"
    s.flags.ignore_permissions = True
    s.save()
