frappe.treeview_settings["Docs Page"] = {
	breadcrumb: "thinkNXG Docs",
	title: __("Docs Pages"),
	get_tree_root: false,
	root_label: "All Pages",
	get_tree_nodes: "thinknxg_docs.api.get_tree_children",
	filters: [
		{
			fieldname: "space",
			fieldtype: "Link",
			options: "Docs Space",
			label: __("Space"),
		},
	],
	fields: [
		{ fieldtype: "Data", fieldname: "title", label: __("Title"), reqd: 1 },
		{
			fieldtype: "Select",
			fieldname: "page_type",
			label: __("Type"),
			options: "Page\nGroup",
			default: "Page",
		},
		{
			fieldtype: "Data",
			fieldname: "slug",
			label: __("Slug"),
			depends_on: "eval:doc.page_type=='Page'",
			description: __("Leave blank to generate from the title"),
		},
	],
	ignore_fields: ["parent_docs_page"],
	onload(treeview) {
		if (!treeview.page.fields_dict.space.get_value()) {
			frappe.db.get_single_value("Docs Settings", "default_space").then((space) => {
				if (space) treeview.page.fields_dict.space.set_value(space);
			});
		}
	},
	toolbar: [
		{
			label: __("View on Website"),
			condition: (node) => !node.is_root && !node.expandable,
			click: (node) => {
				frappe.db.get_value("Docs Page", node.data.value, "route").then((r) => {
					if (r.message && r.message.route) window.open("/" + r.message.route, "_blank");
				});
			},
		},
	],
	extend_toolbar: true,
};
