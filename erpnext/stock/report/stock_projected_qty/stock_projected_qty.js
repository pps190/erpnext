// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.query_reports["Stock Projected Qty"] = {
	"filters": [
		{
			"fieldname":"company",
			"label": __("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"default": frappe.defaults.get_user_default("Company")
		},
		{
			"fieldname":"warehouse",
			"label": __("Warehouse"),
			"fieldtype": "Link",
			"options": "Warehouse",
			"get_query": () => {
				return {
					filters: {
						company: frappe.query_report.get_filter_value('company')
					}
				}
			}
		},
		{
			"fieldname":"item_code",
			"label": __("Item"),
			"fieldtype": "Link",
			"options": "Item",
			"get_query": function() {
				return {
					query: "erpnext.controllers.queries.item_query"
				}
			}
		},
		{
			"fieldname":"item_group",
			"label": __("Item Group"),
			"fieldtype": "Link",
			"options": "Item Group"
		},
		{
			"fieldname":"brand",
			"label": __("Brand"),
			"fieldtype": "Link",
			"options": "Brand"
		},
		{
			"fieldname":"include_uom",
			"label": __("Include UOM"),
			"fieldtype": "Link",
			"options": "UOM"
		}
	],

	formatter: function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (!data || !data.pick_list_details) {
			return value;
		}

		var pick_list_cols = [
			"pick_list",
			"receipt_packing_list",
			"sales_packing_list",
			"customer",
			"sales_order",
		];

		if (pick_list_cols.indexOf(column.fieldname) === -1) {
			return value;
		}

		var raw = data[column.fieldname];
		if (!raw) {
			return value;
		}

		// Single value — render as clickable link
		if (!raw.match(/^\d+ /)) {
			return _spq_format_as_link(raw, column.fieldname);
		}

		// Multiple values — e.g. "2 Pick Lists (PL-001, PL-002)", clickable to open detail dialog
		return (
			'<a href="#" onclick="_spq_show_pick_list_detail(\'' +
			encodeURIComponent(data.pick_list_details) +
			"', '" +
			data.item_code +
			"', '" +
			data.warehouse +
			'\'); return false;" ' +
			'style="color:#7b1fa2; cursor:pointer;">' +
			raw +
			"</a>"
		);
	},
};

function _spq_format_as_link(value, fieldname) {
	var route_map = {
		pick_list: "pick-list",
		receipt_packing_list: "packing-list",
		sales_packing_list: "packing-list",
		customer: "customer",
		sales_order: "sales-order",
	};

	var route = route_map[fieldname];
	if (!route) {
		return value;
	}

	return (
		'<a href="/app/' +
		route + "/" + value +
		'" target="_blank" onclick="event.stopImmediatePropagation()">' +
		value +
		"</a>"
	);
}

window._spq_show_pick_list_detail = function(encoded_details, item_code, warehouse) {
	var details;
	try {
		details = JSON.parse(decodeURIComponent(encoded_details));
	} catch (e) {
		frappe.msgprint(__("Could not parse pick list details."));
		return;
	}

	var rows = details
		.map(function(d) {
			return (
				"<tr>" +
				"<td>" + _spq_make_link("pick-list", d.pick_list) + "</td>" +
				"<td>" + flt(d.qty) + "</td>" +
				"<td>" + _spq_make_link("packing-list", d.receipt_packing_list) + "</td>" +
				"<td>" + _spq_make_link("packing-list", d.sales_packing_list) + "</td>" +
				"<td>" + _spq_make_link("customer", d.customer) +
					(d.customer_name && d.customer_name !== d.customer
						? " <span style='color:#888;'>(" + d.customer_name + ")</span>"
						: "") +
				"</td>" +
				"<td>" + _spq_make_link("sales-order", d.sales_order) + "</td>" +
				"<td>" + _spq_make_link("stock-entry", d.stock_entry) + "</td>" +
				"</tr>"
			);
		})
		.join("");

	var html =
		"<table class='table table-bordered table-hover' style='margin:0;'>" +
		"<thead><tr>" +
		"<th>" + __("Pick List") + "</th>" +
		"<th>" + __("Qty") + "</th>" +
		"<th>" + __("Receipt PL") + "</th>" +
		"<th>" + __("Sales PL") + "</th>" +
		"<th>" + __("Customer") + "</th>" +
		"<th>" + __("Sales Order") + "</th>" +
		"<th>" + __("Stock Entry") + "</th>" +
		"</tr></thead>" +
		"<tbody>" + rows + "</tbody></table>";

	var dialog = new frappe.ui.Dialog({
		title: __("Pick List Details — {0} in {1}", [item_code, warehouse]),
		size: "extra-large",
	});
	dialog.$body.html(html);
	dialog.show();
};

function _spq_make_link(route, value) {
	if (!value) {
		return "\u2014";
	}
	return (
		'<a href="/app/' +
		route + "/" + value +
		'" target="_blank" onclick="event.stopImmediatePropagation()">' +
		value +
		"</a>"
	);
}
