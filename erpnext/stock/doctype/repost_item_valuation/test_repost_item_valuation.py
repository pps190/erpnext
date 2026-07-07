# Copyright (c) 2021, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt


from unittest.mock import MagicMock, call

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings
from frappe.utils import add_days, add_to_date, now, nowdate, today

from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
from erpnext.accounts.utils import repost_gle_for_stock_vouchers
from erpnext.controllers.stock_controller import create_item_wise_repost_entries
from erpnext.stock.doctype.item.test_item import make_item
from erpnext.stock.doctype.purchase_receipt.test_purchase_receipt import make_purchase_receipt
from erpnext.stock.doctype.repost_item_valuation.repost_item_valuation import (
	in_configured_timeslot,
)
from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry
from erpnext.stock.tests.test_utils import StockTestMixin
from erpnext.stock.utils import PendingRepostingError


class TestRepostItemValuation(FrappeTestCase, StockTestMixin):
	def tearDown(self):
		frappe.flags.dont_execute_stock_reposts = False

	def test_repost_time_slot(self):
		repost_settings = frappe.get_doc("Stock Reposting Settings")

		positive_cases = [
			{"limit_reposting_timeslot": 0},
			{
				"limit_reposting_timeslot": 1,
				"start_time": "18:00:00",
				"end_time": "09:00:00",
				"current_time": "20:00:00",
			},
			{
				"limit_reposting_timeslot": 1,
				"start_time": "09:00:00",
				"end_time": "18:00:00",
				"current_time": "12:00:00",
			},
			{
				"limit_reposting_timeslot": 1,
				"start_time": "23:00:00",
				"end_time": "09:00:00",
				"current_time": "2:00:00",
			},
		]

		for case in positive_cases:
			repost_settings.update(case)
			self.assertTrue(
				in_configured_timeslot(repost_settings, case.get("current_time")),
				msg=f"Exepcted true from : {case}",
			)

		negative_cases = [
			{
				"limit_reposting_timeslot": 1,
				"start_time": "18:00:00",
				"end_time": "09:00:00",
				"current_time": "09:01:00",
			},
			{
				"limit_reposting_timeslot": 1,
				"start_time": "09:00:00",
				"end_time": "18:00:00",
				"current_time": "19:00:00",
			},
			{
				"limit_reposting_timeslot": 1,
				"start_time": "23:00:00",
				"end_time": "09:00:00",
				"current_time": "22:00:00",
			},
		]

		for case in negative_cases:
			repost_settings.update(case)
			self.assertFalse(
				in_configured_timeslot(repost_settings, case.get("current_time")),
				msg=f"Exepcted false from : {case}",
			)

	def test_clear_old_logs(self):
		# create 10 logs
		for i in range(1, 20):
			repost_doc = frappe.get_doc(
				doctype="Repost Item Valuation",
				item_code="_Test Item",
				warehouse="_Test Warehouse - _TC",
				based_on="Item and Warehouse",
				posting_date=nowdate(),
				status="Skipped",
				posting_time="00:01:00",
			).insert(ignore_permissions=True)

			repost_doc.load_from_db()
			repost_doc.modified = add_days(now(), days=-i * 10)
			repost_doc.db_update_all()

		logs = frappe.get_all("Repost Item Valuation", filters={"status": "Skipped"})
		self.assertTrue(len(logs) > 10)

		from erpnext.stock.doctype.repost_item_valuation.repost_item_valuation import RepostItemValuation

		RepostItemValuation.clear_old_logs(days=1)

		logs = frappe.get_all("Repost Item Valuation", filters={"status": "Skipped"})
		self.assertTrue(len(logs) == 0)

	def test_create_item_wise_repost_item_valuation_entries(self):
		pr = make_purchase_receipt(
			company="_Test Company with perpetual inventory",
			warehouse="Stores - TCP1",
			get_multiple_items=True,
		)

		rivs = create_item_wise_repost_entries(pr.doctype, pr.name)
		self.assertGreaterEqual(len(rivs), 2)
		self.assertIn("_Test Item", [d.item_code for d in rivs])

		for riv in rivs:
			self.assertEqual(riv.company, "_Test Company with perpetual inventory")
			self.assertEqual(riv.warehouse, "Stores - TCP1")

	def test_deduplication(self):
		def _assert_status(doc, status):
			doc.load_from_db()
			self.assertEqual(doc.status, status)

		riv_args = frappe._dict(
			doctype="Repost Item Valuation",
			item_code="_Test Item",
			warehouse="_Test Warehouse - _TC",
			based_on="Item and Warehouse",
			voucher_type="Sales Invoice",
			voucher_no="SI-1",
			posting_date="2021-01-02",
			posting_time="00:01:00",
		)

		# new repost without any duplicates
		riv1 = frappe.get_doc(riv_args)
		riv1.flags.dont_run_in_test = True
		riv1.submit()
		_assert_status(riv1, "Queued")
		self.assertEqual(riv1.voucher_type, "Sales Invoice")  # traceability
		self.assertEqual(riv1.voucher_no, "SI-1")

		# newer than existing duplicate - riv1
		riv2 = frappe.get_doc(riv_args.update({"posting_date": "2021-01-03"}))
		riv2.flags.dont_run_in_test = True
		riv2.submit()
		riv1.deduplicate_similar_repost()
		_assert_status(riv2, "Skipped")

		# older than exisitng duplicate - riv1
		riv3 = frappe.get_doc(riv_args.update({"posting_date": "2021-01-01"}))
		riv3.flags.dont_run_in_test = True
		riv3.submit()
		riv3.deduplicate_similar_repost()
		_assert_status(riv3, "Queued")
		_assert_status(riv1, "Skipped")

		# unrelated reposts, shouldn't do anything to others.
		riv4 = frappe.get_doc(riv_args.update({"warehouse": "Stores - _TC"}))
		riv4.flags.dont_run_in_test = True
		riv4.submit()
		riv4.deduplicate_similar_repost()
		_assert_status(riv4, "Queued")
		_assert_status(riv3, "Queued")

		# to avoid breaking other tests accidentaly
		riv4.set_status("Skipped")
		riv3.set_status("Skipped")

	def test_stock_freeze_validation(self):

		today = nowdate()

		riv = frappe.get_doc(
			doctype="Repost Item Valuation",
			item_code="_Test Item",
			warehouse="_Test Warehouse - _TC",
			based_on="Item and Warehouse",
			posting_date=today,
			posting_time="00:01:00",
		)
		riv.flags.dont_run_in_test = True  # keep it queued
		riv.submit()

		stock_settings = frappe.get_doc("Stock Settings")
		stock_settings.stock_frozen_upto = today

		self.assertRaises(PendingRepostingError, stock_settings.save)

		riv.set_status("Skipped")

	@change_settings("Stock Reposting Settings", {"item_based_reposting": 0})
	def test_prevention_of_cancelled_transaction_riv(self):
		frappe.flags.dont_execute_stock_reposts = True

		item = make_item()
		warehouse = "_Test Warehouse - _TC"
		old = make_stock_entry(item_code=item.name, to_warehouse=warehouse, qty=2, rate=5)
		_new = make_stock_entry(item_code=item.name, to_warehouse=warehouse, qty=5, rate=10)

		old.cancel()

		riv = frappe.get_last_doc(
			"Repost Item Valuation", {"voucher_type": old.doctype, "voucher_no": old.name}
		)
		self.assertRaises(frappe.ValidationError, riv.cancel)

		riv.db_set("status", "Skipped")
		riv.reload()
		riv.cancel()  # it should cancel now

	def test_queue_progress_serialization(self):
		# Make sure set/tuple -> list behaviour is retained.
		self.assertEqual(
			[["a", "b"], ["c", "d"]],
			sorted(frappe.parse_json(frappe.as_json(set([("a", "b"), ("c", "d")])))),
		)

	def test_gl_repost_progress(self):
		from erpnext.accounts import utils

		# lower numbers to simplify test
		orig_chunk_size = utils.GL_REPOSTING_CHUNK
		utils.GL_REPOSTING_CHUNK = 1
		self.addCleanup(setattr, utils, "GL_REPOSTING_CHUNK", orig_chunk_size)

		doc = frappe.new_doc("Repost Item Valuation")
		doc.db_set = MagicMock()

		vouchers = []
		company = "_Test Company with perpetual inventory"
		posting_date = today()

		for _ in range(3):
			se = make_stock_entry(company=company, qty=1, rate=2, target="Stores - TCP1")
			vouchers.append((se.doctype, se.name))

		repost_gle_for_stock_vouchers(stock_vouchers=vouchers, posting_date=posting_date, repost_doc=doc)
		self.assertIn(call("gl_reposting_index", 1), doc.db_set.mock_calls)
		doc.db_set.reset_mock()

		doc.gl_reposting_index = 1
		repost_gle_for_stock_vouchers(stock_vouchers=vouchers, posting_date=posting_date, repost_doc=doc)

		self.assertNotIn(call("gl_reposting_index", 1), doc.db_set.mock_calls)

	def test_gl_complete_gl_reposting(self):
		from erpnext.accounts import utils

		# lower numbers to simplify test
		orig_chunk_size = utils.GL_REPOSTING_CHUNK
		utils.GL_REPOSTING_CHUNK = 2
		self.addCleanup(setattr, utils, "GL_REPOSTING_CHUNK", orig_chunk_size)

		item = self.make_item().name

		company = "_Test Company with perpetual inventory"

		for _ in range(10):
			make_stock_entry(item=item, company=company, qty=1, rate=10, target="Stores - TCP1")

		# consume
		consumption = make_stock_entry(item=item, company=company, qty=1, source="Stores - TCP1")

		self.assertGLEs(
			consumption,
			[{"credit": 10, "debit": 0}],
			gle_filters={"account": "Stock In Hand - TCP1"},
		)

		# backdated receipt
		backdated_receipt = make_stock_entry(
			item=item,
			company=company,
			qty=1,
			rate=50,
			target="Stores - TCP1",
			posting_date=add_to_date(today(), days=-1),
		)
		self.assertGLEs(
			backdated_receipt,
			[{"credit": 0, "debit": 50}],
			gle_filters={"account": "Stock In Hand - TCP1"},
		)

		# check that original consumption GLe is updated
		self.assertGLEs(
			consumption,
			[{"credit": 50, "debit": 0}],
			gle_filters={"account": "Stock In Hand - TCP1"},
		)

	def test_duplicate_ple_on_repost(self):
		from erpnext.accounts import utils

		# lower numbers to simplify test
		orig_chunk_size = utils.GL_REPOSTING_CHUNK
		utils.GL_REPOSTING_CHUNK = 2
		self.addCleanup(setattr, utils, "GL_REPOSTING_CHUNK", orig_chunk_size)

		rate = 100
		item = self.make_item()
		item.valuation_rate = 90
		item.allow_negative_stock = 1
		item.save()

		company = "_Test Company with perpetual inventory"

		# consume non-existing stock
		sinv = create_sales_invoice(
			company=company,
			posting_date=today(),
			debit_to="Debtors - TCP1",
			income_account="Sales - TCP1",
			expense_account="Cost of Goods Sold - TCP1",
			warehouse="Stores - TCP1",
			update_stock=1,
			currency="INR",
			item_code=item.name,
			cost_center="Main - TCP1",
			qty=1,
			rate=rate,
		)

		# backdated receipt triggers repost
		make_stock_entry(
			item=item.name,
			company=company,
			qty=5,
			rate=rate,
			target="Stores - TCP1",
			posting_date=add_to_date(today(), days=-1),
		)

		ple_entries = frappe.db.get_list(
			"Payment Ledger Entry",
			filters={"voucher_type": sinv.doctype, "voucher_no": sinv.name, "delinked": 0},
		)

		# assert successful deduplication on PLE
		self.assertEqual(len(ple_entries), 1)

		# outstanding should not be affected
		sinv.reload()
		self.assertEqual(sinv.outstanding_amount, 100)

	def test_account_freeze_validation(self):
		today = nowdate()

		riv = frappe.get_doc(
			doctype="Repost Item Valuation",
			item_code="_Test Item",
			warehouse="_Test Warehouse - _TC",
			based_on="Item and Warehouse",
			posting_date=today,
			posting_time="00:01:00",
		)
		riv.flags.dont_run_in_test = True  # keep it queued

		accounts_settings = frappe.get_doc("Accounts Settings")
		accounts_settings.acc_frozen_upto = today
		accounts_settings.frozen_accounts_modifier = ""
		accounts_settings.save()

		self.assertRaises(frappe.ValidationError, riv.save)

		accounts_settings.acc_frozen_upto = ""
		accounts_settings.save()

	@change_settings("Stock Reposting Settings", {"item_based_reposting": 0})
	def test_create_repost_entry_for_cancelled_document(self):
		pr = make_purchase_receipt(
			company="_Test Company with perpetual inventory",
			warehouse="Stores - TCP1",
			get_multiple_items=True,
		)

		self.assertTrue(pr.docstatus == 1)
		self.assertFalse(frappe.db.exists("Repost Item Valuation", {"voucher_no": pr.name}))

		pr.load_from_db()

		pr.cancel()
		self.assertTrue(pr.docstatus == 2)
		self.assertTrue(frappe.db.exists("Repost Item Valuation", {"voucher_no": pr.name}))

	def test_repost_item_valuation_for_closing_stock_balance(self):
		from erpnext.stock.doctype.closing_stock_balance.closing_stock_balance import (
			prepare_closing_stock_balance,
		)

		doc = frappe.new_doc("Closing Stock Balance")
		doc.company = "_Test Company"
		doc.from_date = today()
		doc.to_date = today()
		doc.submit()

		prepare_closing_stock_balance(doc.name)
		doc.load_from_db()
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(doc.status, "Completed")

		riv = frappe.new_doc("Repost Item Valuation")
		riv.update(
			{
				"item_code": "_Test Item",
				"warehouse": "_Test Warehouse - _TC",
				"based_on": "Item and Warehouse",
				"posting_date": today(),
				"posting_time": "00:01:00",
			}
		)

		self.assertRaises(frappe.ValidationError, riv.save)
		doc.cancel()


class TestUpdateRateOnPurchaseReceiptGating(FrappeTestCase):
	"""Regression tests for the internal-supplier valuation_rate overwrite gating.

	update_rate_on_purchase_receipt used to overwrite the voucher item's
	valuation_rate with the SLE outgoing rate for EVERY negative-qty PR/PI SLE of
	an internal supplier. For ordinary inter-company RETURN rows (no
	from_warehouse) that field is the validate-time invoice snapshot that
	make_stock_adjustment_entry needs to regenerate the COGS gap line — the
	overwrite made GL regeneration on repost permanently unbalanced (prod case
	AP-DA1284: Debit and Credit not equal, difference -1.43 = per-unit landed
	cost). The overwrite must fire ONLY for rows with from_warehouse set, whose
	GL books the from-warehouse credit as valuation_rate * stock_qty.
	"""

	def _make_sle(self, voucher_type="Purchase Invoice"):
		return frappe._dict(
			{
				"voucher_type": voucher_type,
				"voucher_no": "TEST-VOUCHER-001",
				"voucher_detail_no": "test-item-row-001",
				"actual_qty": -1.0,
				"outgoing_rate": 26.704,
			}
		)

	def _run(self, sle, is_internal_supplier, from_warehouse, item_row_exists=True):
		from unittest.mock import patch

		from erpnext.stock.stock_ledger import update_entries_after

		obj = update_entries_after.__new__(update_entries_after)

		def cached_value(doctype, name, fieldname):
			if fieldname == "is_internal_supplier":
				return is_internal_supplier
			if fieldname == "is_subcontracted":
				return 0
			return None

		with patch("frappe.db.exists", return_value=item_row_exists), patch(
			"frappe.get_cached_value", side_effect=cached_value
		), patch("frappe.db.get_value", return_value=from_warehouse), patch(
			"frappe.db.set_value"
		) as set_value:
			obj.update_rate_on_purchase_receipt(sle, 26.704)

		return set_value

	def test_no_overwrite_for_internal_supplier_return_without_from_warehouse(self):
		"""The AP-DA1284 case: snapshot must survive the repost."""
		for voucher_type in ("Purchase Invoice", "Purchase Receipt"):
			sle = self._make_sle(voucher_type)
			set_value = self._run(sle, is_internal_supplier=1, from_warehouse=None)
			for c in set_value.call_args_list:
				self.assertNotEqual(
					c.args[2] if len(c.args) > 2 else c.kwargs.get("fieldname"),
					"valuation_rate",
					f"valuation_rate must not be overwritten for {voucher_type} return rows without from_warehouse",
				)

	def test_overwrite_kept_for_internal_transfer_row_with_from_warehouse(self):
		"""Rows with from_warehouse book GL from valuation_rate — sync must continue."""
		sle = self._make_sle()
		set_value = self._run(sle, is_internal_supplier=1, from_warehouse="Stores - _TC")
		set_value.assert_any_call(
			"Purchase Invoice Item", sle.voucher_detail_no, "valuation_rate", sle.outgoing_rate
		)

	def test_no_overwrite_for_external_supplier(self):
		sle = self._make_sle()
		set_value = self._run(sle, is_internal_supplier=0, from_warehouse="Stores - _TC")
		for c in set_value.call_args_list:
			self.assertNotEqual(
				c.args[2] if len(c.args) > 2 else c.kwargs.get("fieldname"), "valuation_rate"
			)

	def test_supplied_item_branch_untouched(self):
		"""Old-flow subcontracting supplied rows (item row does not exist) keep their rate sync."""
		sle = self._make_sle("Purchase Receipt")
		set_value = self._run(sle, is_internal_supplier=1, from_warehouse=None, item_row_exists=False)
		set_value.assert_any_call("Purchase Receipt Item Supplied", sle.voucher_detail_no, "rate", 26.704)
