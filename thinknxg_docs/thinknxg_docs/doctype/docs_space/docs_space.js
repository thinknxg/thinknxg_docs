frappe.ui.form.on("Docs Space", {
	setup(frm) {
		frm.set_query("home_page", () => ({
			filters: { space: frm.doc.name, page_type: "Page" },
		}));
	},

	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Open Docs"), () => window.open("/" + frm.doc.name, "_blank"));
		frm.add_custom_button(__("Pages (Tree)"), () => {
			frappe.route_options = { space: frm.doc.name };
			frappe.set_route("Tree", "Docs Page");
		});

		if (frm.doc.source_llms_url && frappe.user.has_role(["Docs Manager", "System Manager"])) {
			frm.add_custom_button(
				__("Import from Source"),
				() => {
					const d = new frappe.ui.Dialog({
						title: __("Import and rebrand {0}", [frm.doc.title]),
						fields: [
							{
								fieldtype: "HTML",
								options: `<p class="text-muted small">${__(
									"Fetches the index and every page from"
								)} <code>${frappe.utils.escape_html(frm.doc.source_llms_url)}</code>, ${__(
									"applies the rebranding rules and creates or updates pages. Pages marked Lock From Re-import are kept as they are."
								)}</p>`,
							},
							{
								fieldtype: "Int",
								fieldname: "limit",
								label: __("Only the first N pages (0 = all)"),
								default: 0,
							},
							{
								fieldtype: "Check",
								fieldname: "prune",
								label: __("Unpublish pages that are no longer in the source"),
							},
						],
						primary_action_label: __("Start Import"),
						primary_action(values) {
							d.hide();
							frappe
								.call("thinknxg_docs.api.start_import", {
									space: frm.doc.name,
									limit: values.limit || 0,
									prune: values.prune ? 1 : 0,
								})
								.then((r) => {
									frappe.show_alert({
										message: __("Import queued: {0}", [r.message]),
										indicator: "blue",
									});
								});
						},
					});
					d.show();
				},
				__("Actions")
			);
		}

		if (frappe.user.has_role(["Docs Manager", "System Manager"])) {
			frm.add_custom_button(
				__("Re-apply Branding"),
				() => {
					frappe.confirm(
						__("Regenerate all pages of this space from their original text using the current rules?"),
						() =>
							frappe
								.call("thinknxg_docs.api.reapply_branding", { space: frm.doc.name })
								.then(() => frappe.show_alert({ message: __("Rebranding queued"), indicator: "blue" }))
					);
				},
				__("Actions")
			);
			frm.add_custom_button(
				__("Clear Cache"),
				() =>
					frappe
						.call("thinknxg_docs.api.clear_docs_cache", { space: frm.doc.name })
						.then(() => frappe.show_alert({ message: __("Cache cleared"), indicator: "green" })),
				__("Actions")
			);
		}

		if (!frm._tnxg_listening) {
			frm._tnxg_listening = true;
			frappe.realtime.on("thinknxg_docs_import_progress", (data) => {
				if (data.space !== frm.doc.name) return;
				if (data.done >= data.total) {
					frappe.hide_progress();
					frappe.show_alert({ message: __("Import finished"), indicator: "green" });
					frm.reload_doc();
				} else {
					frappe.show_progress(__("Importing {0}", [frm.doc.title]), data.done, data.total, data.title);
				}
			});
		}
	},
});
