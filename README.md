# thinkNXG Docs (`thinknxg_docs`)

A documentation wiki for Frappe v15 / v16 that serves the thinkNXG product docs at
`https://docs.thinknxg.com/<space>` and can import the upstream Frappe documentation,
rebranding it as it goes:

| Upstream | thinkNXG |
|---|---|
| Frappe | thinkNXG |
| Frappe Framework | thinkNXG Framework |
| ERPNext | thinkNXG ERP |
| Frappe HR | thinkNXG HR |
| Frappe Cloud | thinkNXG Cloud |

Four spaces are created on install:

| Route | Title | Upstream source | Published |
|---|---|---|---|
| `/thinknxgerp` | thinkNXG ERP | `https://docs.frappe.io/erpnext` | yes |
| `/thinknxghr` | thinkNXG HR | `https://docs.frappe.io/hr` | no (import first) |
| `/thinknxgframework` | thinkNXG Framework | `https://docs.frappe.io/framework` | no |
| `/thinknxgcloud` | thinkNXG Cloud | `https://docs.frappe.io/cloud` | no |

## Install

```bash
bench new-site docs.thinknxg.com            # or use an existing site
bench get-app /path/to/thinknxg_docs        # or your git URL
bench --site docs.thinknxg.com install-app thinknxg_docs
bench --site docs.thinknxg.com migrate
bench build --app thinknxg_docs             # links /assets/thinknxg_docs
```

Then open **Docs Settings** and tick *Use Default Space as Site Home Page* so
`https://docs.thinknxg.com/` opens thinkNXG ERP.

## Import and rebrand the ERP docs

From the desk: **Docs Space → thinknxgerp → Actions → Import from Source**
(runs on the `long` queue; progress shows in the form and in **Docs Import Log**).

Or from the shell (foreground, prints progress):

```bash
bench --site docs.thinknxg.com thinknxg-docs-import thinknxgerp --limit 20   # trial run
bench --site docs.thinknxg.com thinknxg-docs-import thinknxgerp              # everything
bench --site docs.thinknxg.com thinknxg-docs-import thinknxgerp --prune      # also hide pages removed upstream
```

How it works:

1. Reads `<source>/llms.txt` — the upstream nested index — and recreates the sidebar as
   Groups, Pages and Links (pages listed twice become sidebar Links to one page).
2. Fetches every page's raw markdown (`<page>.md`), downloads its images into this site
   (or links to them — see *Docs Settings → Import*), keeps the original text in
   *Source Content*, and stores the rebranded text in *Content*.
3. Rewrites links between docs pages to the new routes, e.g.
   `https://docs.frappe.io/erpnext/sales-invoice` → `/thinknxgerp/sales-invoice`.

Re-running is safe: items are matched on their import key. Tick **Lock From Re-import** on
any page you edit by hand so a later import keeps your version.

## Rebranding rules

*Docs Settings → Rebranding Rules*. Text rules run in one pass, longest name first, and skip
code blocks, inline code and URLs — so `frappe.get_doc(...)` and `bench get-app erpnext` stay
correct. URL rules rewrite link prefixes (e.g. add
`https://discuss.frappe.io` → `https://community.thinknxg.com`).

After changing rules, use **Re-apply Branding** (on Docs Settings or a Docs Space), or:

```bash
bench --site docs.thinknxg.com thinknxg-docs-rebrand thinknxgerp
```

Pages typed by hand are rebranded on save unless *Skip Automatic Rebranding* is ticked.

Screenshots inside images are not changed — they still show the upstream product UI.
Replace them page by page where it matters.

## Public site

| URL | What |
|---|---|
| `/thinknxgerp` | space home |
| `/thinknxgerp/<slug>` | page |
| `/thinknxgerp/<slug>.md` | page as markdown |
| `/thinknxgerp/llms.txt` · `/llms.txt` | AI-readable indexes |
| `/thinknxgerp/sitemap.xml` · `/docs-sitemap.xml` | sitemaps (add the second to Website Settings → robots.txt) |

Features: space switcher, collapsible sidebar, Ctrl/⌘ K search (current or all spaces),
"On this page" outline with reading progress, previous/next, copy as Markdown,
open in ChatGPT/Claude, print/PDF, "Was this helpful?" feedback, view counts,
light/dark theme, RTL spaces (set *Text Direction* = RTL on the space).

## Roles

* **Docs Manager** — everything, including imports and settings.
* **Docs Editor** — create and edit pages.

## Content licence

The importer copies third-party documentation. Check the licence of the source you import
and keep any attribution it requires — put it in *Docs Settings → Attribution / License
Notice*, which is shown on every page and is never rebranded.

## Tests

```bash
python -m unittest thinknxg_docs.tests.test_core     # parser + rebranding engine, no site needed
```
