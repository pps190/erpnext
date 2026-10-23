# Copyright (c) 2023, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _, qb
from frappe.model.document import Document
from frappe.query_builder import Criterion
from frappe.query_builder.functions import Abs, Sum
from frappe.utils.data import comma_and

from erpnext.accounts.utils import (
	cancel_exchange_gain_loss_journal,
	get_payment_reference_rows,
	remove_ref_from_advance_section,
	unlink_ref_doc_from_payment_entries,
	unlink_ref_row_from_payment_entry,
	update_accounting_ledgers_after_reference_removal,
	update_voucher_outstanding,
)


class UnreconcilePayment(Document):
	def validate(self):
		self.supported_types = ["Payment Entry", "Journal Entry"]
		if not self.voucher_type in self.supported_types:
			frappe.throw(_("Only {0} are supported").format(comma_and(self.supported_types)))

		for alloc in self.allocations:
			if alloc.voucher_detail_no and not get_payment_reference_rows(
				self.voucher_type,
				self.voucher_no,
				alloc.reference_doctype,
				alloc.reference_name,
				row_name=alloc.voucher_detail_no,
			):
				frappe.throw(
					_("Row #{0}: {1} row {2} is not linked to {3}").format(
						alloc.idx, self.voucher_no, alloc.voucher_detail_no, alloc.reference_name
					)
				)

	@frappe.whitelist()
	def get_allocations_from_payment(self):
		allocated_references = []
		ple = qb.DocType("Payment Ledger Entry")
		allocated_references = (
			qb.from_(ple)
			.select(
				ple.account,
				ple.party_type,
				ple.party,
				ple.against_voucher_type.as_("reference_doctype"),
				ple.against_voucher_no.as_("reference_name"),
				Abs(Sum(ple.amount_in_account_currency)).as_("allocated_amount"),
				ple.account_currency,
			)
			.where(
				(ple.docstatus == 1)
				& (ple.voucher_type == self.voucher_type)
				& (ple.voucher_no == self.voucher_no)
				& (ple.voucher_no != ple.against_voucher_no)
			)
			.groupby(ple.against_voucher_type, ple.against_voucher_no)
			.run(as_dict=True)
		)

		return allocated_references

	def add_references(self):
		allocations = self.get_allocations_from_payment()

		for alloc in allocations:
			self.append("allocations", alloc)

	def on_submit(self):
		# todo: more granular unreconciliation
		for alloc in self.allocations:
			doc = frappe.get_doc(alloc.reference_doctype, alloc.reference_name)
			if alloc.voucher_detail_no:
				self.unlink_reference_row(doc, alloc.voucher_detail_no)
			else:
				unlink_ref_doc_from_payment_entries(doc, self.voucher_no)
				cancel_exchange_gain_loss_journal(doc, self.voucher_type, self.voucher_no)
			update_voucher_outstanding(
				alloc.reference_doctype, alloc.reference_name, alloc.account, alloc.party_type, alloc.party
			)
			frappe.db.set_value("Unreconcile Payment Entries", alloc.name, "unlinked", True)

	def unlink_reference_row(self, doc, row_name):
		"""Unlink one allocation row, leaving the voucher's other rows against `doc` linked."""
		row = get_payment_reference_rows(
			self.voucher_type, self.voucher_no, doc.doctype, doc.name, row_name=row_name
		)[0]
		unlink_ref_row_from_payment_entry(doc, self.voucher_type, self.voucher_no, row_name)
		# create_gain_loss_journal stamps the JE row name, or the PE reference idx
		detail_no = row_name if self.voucher_type == "Journal Entry" else row.idx
		cancel_exchange_gain_loss_journal(
			doc, self.voucher_type, self.voucher_no, referenced_detail_no=detail_no
		)

		if not get_payment_reference_rows(self.voucher_type, self.voucher_no, doc.doctype, doc.name):
			# Last row gone: clean up what a full unreconcile would, e.g. a gain/loss journal
			# booked without a row stamp
			update_accounting_ledgers_after_reference_removal(doc.doctype, doc.name, self.voucher_no)
			remove_ref_from_advance_section(doc)
			cancel_exchange_gain_loss_journal(doc, self.voucher_type, self.voucher_no)


@frappe.whitelist()
def doc_has_references(doctype: str = None, docname: str = None):
	if doctype in ["Sales Invoice", "Purchase Invoice"]:
		return frappe.db.count(
			"Payment Ledger Entry",
			filters={"delinked": 0, "against_voucher_no": docname, "amount": ["<", 0]},
		)
	else:
		return frappe.db.count(
			"Payment Ledger Entry",
			filters={"delinked": 0, "voucher_no": docname, "against_voucher_no": ["!=", docname]},
		)


@frappe.whitelist()
def get_linked_payments_for_doc(
	company: str = None, doctype: str = None, docname: str = None
) -> list:
	if company and doctype and docname:
		_dt = doctype
		_dn = docname
		ple = qb.DocType("Payment Ledger Entry")
		if _dt in ["Sales Invoice", "Purchase Invoice"]:
			criteria = [
				(ple.company == company),
				(ple.delinked == 0),
				(ple.against_voucher_no == _dn),
				(ple.amount < 0),
			]

			res = (
				qb.from_(ple)
				.select(
					ple.company,
					ple.voucher_type,
					ple.voucher_no,
					Abs(Sum(ple.amount_in_account_currency)).as_("allocated_amount"),
					ple.account_currency,
				)
				.where(Criterion.all(criteria))
				.groupby(ple.voucher_no, ple.against_voucher_no)
				.having(qb.Field("allocated_amount") > 0)
				.run(as_dict=True)
			)
			return split_by_reference_row(res, ref_type=_dt, ref_no=_dn)
		else:
			criteria = [
				(ple.company == company),
				(ple.delinked == 0),
				(ple.voucher_no == _dn),
				(ple.against_voucher_no != _dn),
			]

			query = (
				qb.from_(ple)
				.select(
					ple.company,
					ple.against_voucher_type.as_("voucher_type"),
					ple.against_voucher_no.as_("voucher_no"),
					Abs(Sum(ple.amount_in_account_currency)).as_("allocated_amount"),
					ple.account_currency,
				)
				.where(Criterion.all(criteria))
				.groupby(ple.against_voucher_no)
			)
			res = query.run(as_dict=True)
			return split_by_reference_row(res, payment_type=_dt, payment_name=_dn)
	return []


def split_by_reference_row(
	res: list, payment_type: str = None, payment_name: str = None, ref_type=None, ref_no=None
) -> list:
	"""
	Replace each voucher-level allocation with one line per Journal Entry Account /
	Payment Entry Reference row, so a single allocation can be unreconciled on its own
	(pps190/erpnext#52). Pass the payment side or the reference side the caller is on.
	"""
	out = []
	for x in res:
		rows = get_payment_reference_rows(
			payment_type or x.voucher_type,
			payment_name or x.voucher_no,
			ref_type or x.voucher_type,
			ref_no or x.voucher_no,
		)
		if not rows:
			out.append(x)
			continue
		for row in rows:
			out.append(
				frappe._dict(x, voucher_detail_no=row.name, allocated_amount=row.allocated_amount)
			)
	return out


@frappe.whitelist()
def create_unreconcile_doc_for_selection(selections=None):
	if selections:
		selections = frappe.json.loads(selections)
		# one Unreconcile Payment per payment voucher; a row carrying voucher_detail_no
		# unlinks only that allocation row
		by_voucher = {}
		for row in selections:
			key = (row.get("company"), row.get("voucher_type"), row.get("voucher_no"))
			by_voucher.setdefault(key, []).append(row)

		for (company, voucher_type, voucher_no), rows in by_voucher.items():
			unrecon = frappe.new_doc("Unreconcile Payment")
			unrecon.company = company
			unrecon.voucher_type = voucher_type
			unrecon.voucher_no = voucher_no
			allocations = unrecon.get_allocations_from_payment()

			for row in rows:
				for alloc in allocations:
					if not (
						alloc.reference_doctype == row.get("against_voucher_type")
						and alloc.reference_name == row.get("against_voucher_no")
					):
						continue
					if row.get("voucher_detail_no"):
						detail = get_payment_reference_rows(
							voucher_type,
							voucher_no,
							alloc.reference_doctype,
							alloc.reference_name,
							row_name=row.get("voucher_detail_no"),
						)
						allocated_amount = detail[0].allocated_amount if detail else 0
						unrecon.append(
							"allocations",
							dict(
								alloc,
								voucher_detail_no=row.get("voucher_detail_no"),
								allocated_amount=allocated_amount,
							),
						)
					else:
						unrecon.append("allocations", alloc)

			if not unrecon.allocations:
				frappe.throw(_("{0} has nothing left to unreconcile").format(voucher_no))
			unrecon.save().submit()
