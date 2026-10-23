app_name = "thinknxg_docs"
app_title = "thinkNXG Docs"
app_publisher = "Kreatao"
app_description = "thinkNXG documentation wiki — imports and rebrands upstream docs into thinkNXG spaces"
app_email = "kreataothinkcadd@gmail.com"
app_license = "mit"

required_apps = ["frappe"]

add_to_apps_screen = [
    {
        "name": "thinknxg_docs",
        "logo": "/assets/thinknxg_docs/images/logo.svg",
        "title": "thinkNXG Docs",
        "route": "/app/thinknxg-docs",
    }
]

# Website: serve /<space>/... before Frappe's own renderers
page_renderer = ["thinknxg_docs.renderer.DocsRenderer"]

# Desk tree view for Docs Page
treeviews = ["Docs Page"]

before_install = "thinknxg_docs.install.before_install"
after_install = "thinknxg_docs.install.after_install"
after_migrate = "thinknxg_docs.install.after_migrate"

scheduler_events = {
    "hourly": ["thinknxg_docs.tasks.flush_page_views"],
}
