# Tax-Only Debit Note — Design Document

**Date**: 2026-04-06

## Problem

When a Purchase Invoice has tax/charge rows that need to be reversed (e.g., a -$80 shipping charge refund), the standard approach is to create a Debit Note (Purchase Invoice with `is_return = 1`). However, ERPNext requires at least one item row on every Purchase Invoice and Sales Invoice (`items` table has `reqd: 1`), making it impossible to create a debit note that only contains tax adjustments.

The workaround of using a Journal Entry works but loses the connection to the supplier's payable account workflow and doesn't appear in Payment Reconciliation as a proper invoice.

## Approach

Remove the mandatory constraint on the items table and fix all code paths that assume items exist.

## Analysis — What breaks with empty items

### Frappe layer
- `_validate_mandatory()` in `frappe/model/base_document.py:708` — checks `self.get(df.fieldname) in (None, [])` for reqd fields → **blocks save**. Fix: remove `reqd: 1` from JSON.

### Tax calculation
- `taxes_and_totals.py:40` — `if not len(self._items): return` skips all calculation → `grand_total` stays 0 → supplier GL entry not created → only 1 GL entry → "Incorrect number of GL Entries" error. Fix: allow calculation to proceed when taxes exist.

### Purchase Invoice
- `purchase_invoice.py:978` — `item` variable referenced after `for item in self.get("items")` loop (asset update) → `UnboundLocalError`. Fix: guard with `if self.get("items")`.

### Accounts Controller
- `accounts_controller.py:1989` — `self.get("items")[0].get("purchase_order")` → `IndexError`. Fix: guard with `if self.get("items") else None`.

### Return validation
- `sales_and_purchase_return.py:158` — requires at least one item with negative qty → **blocks submit**. Fix: skip validation when items empty.

### Safe (no changes needed)
- `make_supplier_gl_entry()` — independent of items, uses `grand_total`
- `make_tax_gl_entries()` — iterates over `self.get("taxes")`, not items
- `set_expense_account()` — loops over items (empty = no-op)
- `set_against_expense_account()` — returns empty string (acceptable)
- `validate_qty_is_not_zero()` — skipped for returns
- `make_precision_loss_gl_entry()` — uses aggregate values
- `make_payment_gl_entries()` — checks conditions first
- Sales Invoice `make_item_gl_entries()` — no unbound variable issue (no code after loop)

## Test scenarios

1. **PI debit note with tax only** — create PI with `is_return=1`, no items, one Actual tax row → should save and submit, GL entries balanced
2. **SI credit note with tax only** — same for Sales Invoice
3. **PI debit note with return_against** — should still require items (existing behavior preserved)
4. **Normal PI without items** — should save (no practical use but technically allowed)
5. **Multi-currency tax-only debit note** — company base AED, invoice USD, tax in USD → GL in AED with correct exchange rate
