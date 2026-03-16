import frappe


def execute():
	"""Clear saved Configure Columns settings for Payment Entry Reference and
	Payment Reconciliation Invoice grids so users see the new default column layout."""
	frappe.db.delete(
		"DefaultValue",
		{"defkey": ["in", ["payment_entry_reference:list_settings", "payment_reconciliation_invoice:list_settings"]]},
	)
