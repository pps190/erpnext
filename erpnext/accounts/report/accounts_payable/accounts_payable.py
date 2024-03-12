# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


from erpnext.accounts.report.accounts_receivable.accounts_receivable import ReceivablePayableReport
from frappe.utils import nowdate

def execute(filters=None):
	args = {
		"account_type": "Payable",
		"naming_by": ["Buying Settings", "supp_master_name"],
	}
	r = ReceivablePayableReport(filters).run(args)

	for d in r[1]:
		if "bill_date" not in d or not d["bill_date"]:
			d["bill_date"] = d["posting_date"]

	r[1].sort(key=lambda b: b["bill_date"])
	return r
