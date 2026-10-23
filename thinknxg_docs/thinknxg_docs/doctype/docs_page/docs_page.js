const tnxgSlugify = (s) =>
	(s || "")
		.toLowerCase()
		.replace(/[^a-z0-9/_-]+/g, "-")
		.replace(/-{2,}/g, "-")
		.replace(/^[-/]+|[-/]+$/g, "");

frappe.ui.form.on("Docs Page", {
	setup(frm) {
		frm.set_query("parent_docs_page", () => ({
			filters: { space: frm.doc.space, page_type: "Group", name: ["!=", frm.doc.name || ""] },
		}));
		frm.set_query("link_to_page", () => ({
			filters: { space: frm.doc.space, page_type: "Page" },
		}));
	},

	refresh(frm) {
		if (!frm.is_new() && frm.doc.page_type === "Page" && frm.doc.route) {
			frm.add_custom_button(__("View on Website"), () => window.open("/" + frm.doc.route, "_blank"));
		}
		if (!frm.is_new() && frm.doc.space) {
			frm.add_custom_button(__("Space Tree"), () => {
				frappe.route_options = { space: frm.doc.space };
				frappe.set_route("Tree", "Docs Page");
			});
		}
		if (frm.doc.source_url) {
			frm.set_intro(
				__("Imported from source. Re-import overwrites this page unless <b>Lock From Re-import</b> is ticked."),
				frm.doc.lock_from_import ? "green" : "blue"
			);
		}
	},

	title(frm) {
		if (frm.doc.page_type === "Page" && (frm.is_new() || !frm.doc.slug)) {
			frm.set_value("slug", tnxgSlugify(frm.doc.title));
		}
	},

	slug(frm) {
		const clean = tnxgSlugify(frm.doc.slug);
		if (clean !== frm.doc.slug) frm.set_value("slug", clean);
	},
});
