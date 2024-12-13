frappe.listview_settings['Material Request'] = {
	add_fields: ["material_request_type", "status", "per_ordered", "per_received", "transfer_status"],
	get_indicator: function(doc) {
		var precision = frappe.defaults.get_default("float_precision");
		if (doc.status=="Stopped") {
			return [__("Stopped"), "red", "status,=,Stopped"];
		} else if (doc.transfer_status && doc.docstatus != 2) {
			if (doc.transfer_status == "Not Started") {
				return [__("Not Started"), "orange"];
			} else if (doc.transfer_status == "In Transit") {
				return [__("In Transit"), "yellow"];
			} else if (doc.transfer_status == "Completed") {
				return [__("Completed"), "green"];
			}
		} else if (doc.docstatus==1 && flt(doc.per_ordered, precision) == 0) {
			return [__("Pending"), "orange", "per_ordered,=,0"];
		}  else if (doc.docstatus==1 && flt(doc.per_ordered, precision) < 100) {
			return [__("Partially ordered"), "yellow", "per_ordered,<,100"];
		} else if (doc.docstatus==1 && flt(doc.per_ordered, precision) == 100) {
			if (doc.material_request_type == "Purchase" && flt(doc.per_received, precision) < 100 && flt(doc.per_received, precision) > 0) {
				return [__("Partially Received"), "yellow", "per_received,<,100"];
			} else if (doc.material_request_type == "Purchase" && flt(doc.per_received, precision) == 100) {
				return [__("Received"), "green", "per_received,=,100"];
			} else if (doc.material_request_type == "Purchase") {
				return [__("Ordered"), "green", "per_ordered,=,100"];
			} else if (doc.material_request_type == "Material Transfer") {
				return [__("Transfered"), "green", "per_ordered,=,100"];
			} else if (doc.material_request_type == "Material Issue") {
				return [__("Issued"), "green", "per_ordered,=,100"];
			} else if (doc.material_request_type == "Customer Provided") {
				return [__("Received"), "green", "per_ordered,=,100"];
			} else if (doc.material_request_type == "Manufacture") {
				return [__("Manufactured"), "green", "per_ordered,=,100"];
			}
		}
	}
};


/*
Add upload from excel dialog.
 */
function upload_part_material_request_from_excel(listview) {
	listview.page.add_button(__("Upload"), function () {
		const dialog = new frappe.ui.Dialog({
			title: __("Upload Material Transfer Request"),
			fields: [
				{
					fieldname: "material_request_type",
					label: __("Material Request Type"),
					fieldtype: "Select",
					options: frappe.get_meta("Material Request").fields.find(df => df.fieldname === "material_request_type").options,
					default: "Material Transfer",
					read_only: 1,
					reqd: 1,
				},
				{
					fieldname: "set_from_warehouse",
					label: __("Source Warehouse"),
					fieldtype: "Link",
					options: "Warehouse",
					reqd: 1,
					depends_on: "eval:doc.material_request_type",
				},
				{
					fieldname: "set_warehouse",
					label: __("Target Warehouse"),
					fieldtype: "Link",
					options: "Warehouse",
					reqd: 1,
					depends_on: "eval:doc.set_from_warehouse",
				},
				{
					fieldname: "file_upload",
					label: __("Upload"),
					fieldtype: "Attach",
					reqd: 1,
					depends_on: "eval:doc.set_warehouse",
				},
			],
			primary_action_label: __("Upload"),
			primary_action(kwargs) {
				// TODO: try upload.
				frappe.call({
					method: "erpnext.stock.doctype.material_request.material_request.make_material_request_from_upload",
					args: { kwargs },
					btn: this,
					callback({ message }) {
						frappe.set_route(message);
					}
				});
			},
			secondary_action_label: __("Cancel"),
			secondary_action() {
				dialog.hide();
			},
		}).show();
	});
}

frappe.listview_settings["Material Request"].onload = upload_part_material_request_from_excel;
