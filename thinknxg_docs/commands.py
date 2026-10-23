"""bench commands

  bench --site <site> thinknxg-docs-import thinknxgerp [--limit 20] [--prune]
  bench --site <site> thinknxg-docs-rebrand [thinknxgerp]
"""

import click
from frappe.commands import get_site, pass_context


@click.command("thinknxg-docs-import")
@click.argument("space")
@click.option("--limit", default=0, type=int, help="Import only the first N pages (for a trial run)")
@click.option("--prune", is_flag=True, default=False, help="Unpublish pages no longer in the source index")
@pass_context
def docs_import(context, space, limit=0, prune=False):
    """Import and rebrand a docs space from its upstream source (runs in the foreground)."""
    import frappe

    site = get_site(context)
    frappe.init(site=site)
    frappe.connect()
    try:
        frappe.set_user("Administrator")
        from thinknxg_docs.importer import create_log, run_import

        log = create_log(space, limit, int(prune))
        frappe.db.commit()
        counts = run_import(log, limit=limit, prune=int(prune), verbose=True)
        click.secho(f"Import finished: {counts} (log {log})", fg="green")
    finally:
        frappe.destroy()


@click.command("thinknxg-docs-rebrand")
@click.argument("space", required=False)
@pass_context
def docs_rebrand(context, space=None):
    """Re-apply the current rebranding rules to all pages (or one space)."""
    import frappe

    site = get_site(context)
    frappe.init(site=site)
    frappe.connect()
    try:
        frappe.set_user("Administrator")
        from thinknxg_docs.importer import reapply_branding

        changed = reapply_branding(space)
        click.secho(f"Rebranded {changed} page(s)", fg="green")
    finally:
        frappe.destroy()


commands = [docs_import, docs_rebrand]
