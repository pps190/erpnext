# Tax-Only Debit Note Technical Guide

**Last Updated**: 2026-04-06

## Overview

This feature allows Purchase Invoices and Sales Invoices to be created, saved, and submitted **without any item rows** — containing only tax/charge rows. The primary use case is creating debit notes to reverse tax or charge amounts that cannot be attached to specific inventory items.

### Key design decisions

- **Minimal changes to core** — only removed the `reqd` constraint on the items table and added guards where empty items would cause runtime errors
- **No new validation** — normal (non-return) invoices without items are technically allowed but have no practical use case; the UI still shows items as a table so users won't accidentally skip them
- **Tax calculation preserved** — `taxes_and_totals.py` has a dedicated code path for empty items that correctly computes `grand_total` from tax rows alone

## Changes

### 1. Items table no longer mandatory

**Files**: `purchase_invoice.json`, `sales_invoice.json`

Removed `"reqd": 1` from the `items` Table field definition. This allows Frappe's `_validate_mandatory()` to pass when the items child table is empty.

Previously, any attempt to save a PI or SI with zero items would raise `MandatoryError` from `frappe.model.base_document._get_missing_mandatory_fields()` (checks `self.get(df.fieldname) in (None, [])` for reqd Table fields).

### 2. Tax calculation for empty items

**File**: `erpnext/controllers/taxes_and_totals.py` — `calculate_taxes()`

**Before**: `calculate()` returned early if `not len(self._items)`, skipping all tax and total computation. This left `grand_total = 0` even when tax rows existed, causing the supplier/customer GL entry to be skipped (guarded by `if grand_total`), which left only 1 GL entry and triggered the "Incorrect number of General Ledger Entries" error.

**After**: The early return now checks `not len(self._items) and not self.doc.get("taxes")`. When items are empty but taxes exist, `calculate()` proceeds. A new branch in `calculate_taxes()` handles the empty-items case:

- For each tax row (only Actual charge types are meaningful without items):
  - Sets `tax_amount_after_discount_amount = tax_amount`
  - Calls `round_off_totals()`, `set_cumulative_total()`, `_set_in_company_currency()`
- `calculate_totals()` then picks up `taxes[-1].total` as `grand_total`

This produces the correct GL entries: one for the supplier/customer payable account and one for the tax/charge account.

### 3. Asset update guard

**File**: `erpnext/accounts/doctype/purchase_invoice/purchase_invoice.py` — `make_item_gl_entries()`

The asset update block (lines ~978-983) referenced `item` variable after the `for item in self.get("items")` loop. With empty items, the loop never executes and `item` is unbound, causing `UnboundLocalError`.

**Fix**: Wrapped the asset block in `if self.get("items"):`.

### 4. Payment schedule order details

**File**: `erpnext/controllers/accounts_controller.py` — `get_order_details()`

This method accessed `self.get("items")[0]` to find a linked Purchase Order or Sales Order. With empty items, this raises `IndexError`.

**Fix**: Added guard `if self.get("items") else None` — returns `None` when items is empty. Downstream code (`linked_order_has_payment_terms`) already guards with `if po_or_so and ...`.

### 5. Return item validation bypass

**File**: `erpnext/controllers/sales_and_purchase_return.py` — `validate_returned_items()`

This function requires at least one item with negative qty for return documents. For tax-only debit notes there are no items to validate.

**Fix**: Added early return `if not doc.get("items"): return` at the top.

## GL Entry Structure

For a tax-only debit note with a single tax charge of -$2 USD:

| Account | Debit | Credit | Party |
|---------|-------|--------|-------|
| Creditors (payable) | $2.00 | | Supplier |
| COGS / Expense | | $2.00 | |

The debit to creditors reduces the amount owed to the supplier. The credit to the expense account reverses the original charge.

## Constraints

- **Standalone debit notes only**: If `return_against` is set (linking to original invoice), `validate_returned_items()` still requires items. Tax-only debit notes should NOT set `return_against`.
- **Only Actual charge type**: Without items, percentage-based tax calculations produce zero. Only `charge_type = "Actual"` is meaningful.
- **No stock impact**: Tax-only invoices have `update_stock = 0` by definition (no items to receive/deliver).
