# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


import json

import frappe
from frappe import _
from frappe.utils import flt, today
from pypika.terms import ExistsCriterion

from erpnext.accounts.doctype.pos_invoice.pos_invoice import get_pos_reserved_qty
from erpnext.stock.utils import (
	is_reposting_item_valuation_in_progress,
	update_included_uom_in_report,
)


def execute(filters=None):
	is_reposting_item_valuation_in_progress()
	filters = frappe._dict(filters or {})
	include_uom = filters.get("include_uom")
	columns = get_columns()
	bin_list = get_bin_list(filters)
	item_map = get_item_map(filters.get("item_code"), include_uom)

	# Pre-build pick list lookup from active (To Pack) Pick Lists
	pick_list_map = get_pick_list_map()

	warehouse_company = {}
	data = []
	conversion_factors = []
	for bin in bin_list:
		item = item_map.get(bin.item_code)

		if not item:
			# likely an item that has reached its end of life
			continue

		# item = item_map.setdefault(bin.item_code, get_item(bin.item_code))
		company = warehouse_company.setdefault(
			bin.warehouse, frappe.db.get_value("Warehouse", bin.warehouse, "company")
		)

		if filters.brand and filters.brand != item.brand:
			continue

		elif filters.item_group and filters.item_group != item.item_group:
			continue

		elif filters.company and filters.company != company:
			continue

		re_order_level = re_order_qty = 0

		for d in item.get("reorder_levels"):
			if d.warehouse == bin.warehouse:
				re_order_level = d.warehouse_reorder_level
				re_order_qty = d.warehouse_reorder_qty

		shortage_qty = 0
		if (re_order_level or re_order_qty) and re_order_level > bin.projected_qty:
			shortage_qty = re_order_level - flt(bin.projected_qty)

		reserved_qty_for_pos = get_pos_reserved_qty(bin.item_code, bin.warehouse)
		if reserved_qty_for_pos:
			bin.projected_qty -= reserved_qty_for_pos

		key = (bin.item_code, bin.warehouse)
		pl_details = pick_list_map.get(key, [])
		pl_display, rpl_display, spl_display, cust_display, so_display = \
			format_pick_list_columns(pl_details)

		data.append(
			[
				item.name,
				item.item_name,
				item.description,
				item.item_group,
				item.brand,
				bin.warehouse,
				item.stock_uom,
				bin.actual_qty,
				pl_display,
				rpl_display,
				spl_display,
				cust_display,
				so_display,
				json.dumps(pl_details) if pl_details else "",
				bin.planned_qty,
				bin.indented_qty,
				bin.ordered_qty,
				bin.reserved_qty,
				bin.reserved_qty_for_production,
				bin.reserved_qty_for_production_plan,
				bin.reserved_qty_for_sub_contract,
				reserved_qty_for_pos,
				bin.projected_qty,
				re_order_level,
				re_order_qty,
				shortage_qty,
			]
		)

		if include_uom:
			conversion_factors.append(item.conversion_factor)

	update_included_uom_in_report(columns, data, include_uom, conversion_factors)
	return columns, data


def get_columns():
	return [
		{
			"label": _("Item Code"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 140,
		},
		{"label": _("Item Name"), "fieldname": "item_name", "width": 100},
		{"label": _("Description"), "fieldname": "description", "width": 200},
		{
			"label": _("Item Group"),
			"fieldname": "item_group",
			"fieldtype": "Link",
			"options": "Item Group",
			"width": 100,
		},
		{
			"label": _("Brand"),
			"fieldname": "brand",
			"fieldtype": "Link",
			"options": "Brand",
			"width": 100,
		},
		{
			"label": _("Warehouse"),
			"fieldname": "warehouse",
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 120,
		},
		{
			"label": _("UOM"),
			"fieldname": "stock_uom",
			"fieldtype": "Link",
			"options": "UOM",
			"width": 100,
		},
		{
			"label": _("Actual Qty"),
			"fieldname": "actual_qty",
			"fieldtype": "Float",
			"width": 100,
			"convertible": "qty",
		},
		{
			"label": _("Pick List"),
			"fieldname": "pick_list",
			"fieldtype": "Data",
			"width": 130,
		},
		{
			"label": _("Receipt PL"),
			"fieldname": "receipt_packing_list",
			"fieldtype": "Data",
			"width": 130,
		},
		{
			"label": _("Sales PL"),
			"fieldname": "sales_packing_list",
			"fieldtype": "Data",
			"width": 130,
		},
		{
			"label": _("Customer"),
			"fieldname": "customer",
			"fieldtype": "Data",
			"width": 140,
		},
		{
			"label": _("Sales Order"),
			"fieldname": "sales_order",
			"fieldtype": "Data",
			"width": 130,
		},
		{
			"label": _("Pick List Details"),
			"fieldname": "pick_list_details",
			"fieldtype": "Data",
			"hidden": 1,
		},
		{
			"label": _("Planned Qty"),
			"fieldname": "planned_qty",
			"fieldtype": "Float",
			"width": 100,
			"convertible": "qty",
		},
		{
			"label": _("Requested Qty"),
			"fieldname": "indented_qty",
			"fieldtype": "Float",
			"width": 110,
			"convertible": "qty",
		},
		{
			"label": _("Ordered Qty"),
			"fieldname": "ordered_qty",
			"fieldtype": "Float",
			"width": 100,
			"convertible": "qty",
		},
		{
			"label": _("Reserved Qty"),
			"fieldname": "reserved_qty",
			"fieldtype": "Float",
			"width": 100,
			"convertible": "qty",
		},
		{
			"label": _("Reserved for Production"),
			"fieldname": "reserved_qty_for_production",
			"fieldtype": "Float",
			"width": 100,
			"convertible": "qty",
		},
		{
			"label": _("Reserved for Production Plan"),
			"fieldname": "reserved_qty_for_production_plan",
			"fieldtype": "Float",
			"width": 100,
			"convertible": "qty",
		},
		{
			"label": _("Reserved for Sub Contracting"),
			"fieldname": "reserved_qty_for_sub_contract",
			"fieldtype": "Float",
			"width": 100,
			"convertible": "qty",
		},
		{
			"label": _("Reserved for POS Transactions"),
			"fieldname": "reserved_qty_for_pos",
			"fieldtype": "Float",
			"width": 100,
			"convertible": "qty",
		},
		{
			"label": _("Projected Qty"),
			"fieldname": "projected_qty",
			"fieldtype": "Float",
			"width": 100,
			"convertible": "qty",
		},
		{
			"label": _("Reorder Level"),
			"fieldname": "re_order_level",
			"fieldtype": "Float",
			"width": 100,
			"convertible": "qty",
		},
		{
			"label": _("Reorder Qty"),
			"fieldname": "re_order_qty",
			"fieldtype": "Float",
			"width": 100,
			"convertible": "qty",
		},
		{
			"label": _("Shortage Qty"),
			"fieldname": "shortage_qty",
			"fieldtype": "Float",
			"width": 100,
			"convertible": "qty",
		},
	]


def get_bin_list(filters):
	bin = frappe.qb.DocType("Bin")
	query = (
		frappe.qb.from_(bin)
		.select(
			bin.item_code,
			bin.warehouse,
			bin.actual_qty,
			bin.planned_qty,
			bin.indented_qty,
			bin.ordered_qty,
			bin.reserved_qty,
			bin.reserved_qty_for_production,
			bin.reserved_qty_for_sub_contract,
			bin.reserved_qty_for_production_plan,
			bin.projected_qty,
		)
		.orderby(bin.item_code, bin.warehouse)
	)

	if filters.item_code:
		query = query.where(bin.item_code == filters.item_code)

	if filters.warehouse:
		warehouse_details = frappe.db.get_value(
			"Warehouse", filters.warehouse, ["lft", "rgt"], as_dict=1
		)

		if warehouse_details:
			wh = frappe.qb.DocType("Warehouse")
			query = query.where(
				ExistsCriterion(
					frappe.qb.from_(wh)
					.select(wh.name)
					.where(
						(wh.lft >= warehouse_details.lft)
						& (wh.rgt <= warehouse_details.rgt)
						& (bin.warehouse == wh.name)
					)
				)
			)

	bin_list = query.run(as_dict=True)

	return bin_list


def get_item_map(item_code, include_uom):
	"""Optimization: get only the item doc and re_order_levels table"""

	bin = frappe.qb.DocType("Bin")
	item = frappe.qb.DocType("Item")

	query = (
		frappe.qb.from_(item)
		.select(item.name, item.item_name, item.description, item.item_group, item.brand, item.stock_uom)
		.where(
			(item.is_stock_item == 1)
			& (item.disabled == 0)
			& (
				(item.end_of_life > today()) | (item.end_of_life.isnull()) | (item.end_of_life == "0000-00-00")
			)
			& (ExistsCriterion(frappe.qb.from_(bin).select(bin.name).where(bin.item_code == item.name)))
		)
	)

	if item_code:
		query = query.where(item.item_code == item_code)

	if include_uom:
		ucd = frappe.qb.DocType("UOM Conversion Detail")
		query = query.left_join(ucd).on((ucd.parent == item.name) & (ucd.uom == include_uom))

	items = query.run(as_dict=True)

	ir = frappe.qb.DocType("Item Reorder")
	query = frappe.qb.from_(ir).select("*")

	if item_code:
		query = query.where(ir.parent == item_code)

	reorder_levels = frappe._dict()
	for d in query.run(as_dict=True):
		if d.parent not in reorder_levels:
			reorder_levels[d.parent] = []

		reorder_levels[d.parent].append(d)

	item_map = frappe._dict()
	for item in items:
		item["reorder_levels"] = reorder_levels.get(item.name) or []
		item_map[item.name] = item

	return item_map


def format_pick_list_columns(pl_details):
	"""Return display values for pick list related columns.

	Single value: the name directly.
	Multiple values: 'N Pick Lists' etc.
	No value: empty string.
	"""
	if not pl_details:
		return "", "", "", "", ""

	pick_lists = list({d["pick_list"] for d in pl_details if d.get("pick_list")})
	receipt_pls = list({d["receipt_packing_list"] for d in pl_details if d.get("receipt_packing_list")})
	sales_pls = list({d["sales_packing_list"] for d in pl_details if d.get("sales_packing_list")})
	customers = list({d["customer"] for d in pl_details if d.get("customer")})
	sales_orders = list({d["sales_order"] for d in pl_details if d.get("sales_order")})

	def _fmt(items, plural):
		if not items:
			return ""
		if len(items) == 1:
			return items[0]
		return f"{len(items)} {plural}"

	return (
		_fmt(pick_lists, "Pick Lists"),
		_fmt(receipt_pls, "Receipt PLs"),
		_fmt(sales_pls, "Sales PLs"),
		_fmt(customers, "Customers"),
		_fmt(sales_orders, "Sales Orders"),
	)


def get_pick_list_map():
	"""Query from 'To Pack' Pick Lists outward to find (item, warehouse) mappings.

	Starts from the small set of active Pick Lists rather than the large Bin/SLE tables.
	Returns dict: {(item_code, warehouse): [{pick_list, qty, customer, ...}, ...]}
	"""
	result = frappe.db.sql("""
		SELECT
			sle.item_code,
			sle.warehouse,
			sle.actual_qty as sle_qty,
			se.name as stock_entry,
			se.pick_list,
			pl.customer,
			pl.customer_name,
			pli.sales_order,
			pli.source_receipt_packing_list as receipt_packing_list,
			(
				SELECT plv.parent
				FROM `tabPacking List Voucher` plv
				WHERE plv.voucher_no = pl.name
				  AND plv.voucher_type = 'Pick List'
				LIMIT 1
			) as sales_packing_list
		FROM `tabPick List` pl
		INNER JOIN `tabStock Entry` se ON se.pick_list = pl.name
			AND se.docstatus = 1
		INNER JOIN `tabStock Ledger Entry` sle ON sle.voucher_no = se.name
			AND sle.voucher_type = 'Stock Entry'
			AND sle.is_cancelled = 0
			AND sle.actual_qty > 0
		LEFT JOIN `tabPick List Item` pli ON pli.parent = pl.name
			AND pli.item_code = sle.item_code
		WHERE pl.status = 'To Pack'
			AND pl.docstatus = 1
		ORDER BY sle.posting_date DESC, sle.posting_time DESC
	""", as_dict=True)

	pick_list_map = {}
	seen = {}

	for row in result:
		key = (row.item_code, row.warehouse)
		pl_key = (row.item_code, row.warehouse, row.pick_list)

		if pl_key in seen:
			continue
		seen[pl_key] = True

		pick_list_map.setdefault(key, []).append({
			"pick_list": row.pick_list,
			"qty": flt(row.sle_qty),
			"customer": row.customer or "",
			"customer_name": row.customer_name or "",
			"sales_order": row.sales_order or "",
			"receipt_packing_list": row.receipt_packing_list or "",
			"sales_packing_list": row.sales_packing_list or "",
			"stock_entry": row.stock_entry,
		})

	return pick_list_map
