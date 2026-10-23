frappe.ui.form.on("Docs Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Re-apply Branding to All Spaces"), () => {
			if (frm.is_dirty()) {
				frappe.msgprint(__("Save the settings first."));
				return;
			}
			frappe.confirm(
				__("Regenerate every page from its original text with the current rules?"),
				() =>
					frappe
						.call("thinknxg_docs.api.reapply_branding")
						.then(() => frappe.show_alert({ message: __("Rebranding queued"), indicator: "blue" }))
			);
		});
		frm.add_custom_button(__("Open Docs Site"), () =>
			window.open("/" + (frm.doc.default_space || ""), "_blank")
		);
	},
});
