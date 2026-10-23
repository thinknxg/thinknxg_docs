frappe.ui.form.on("Docs Import Log", {
	refresh(frm) {
		if (["Queued", "Running"].includes(frm.doc.status)) {
			setTimeout(() => frm.reload_doc(), 5000);
		}
		if (frm.doc.space) {
			frm.add_custom_button(__("Open Space"), () => frappe.set_route("Form", "Docs Space", frm.doc.space));
		}
	},
});
