# Tax-Only Debit Note — Test Scenarios

**Date**: 2026-04-06

## Test 1: PI debit note with tax only — save and submit

**Precondition**: Existing submitted PI with tax charges (e.g. AP-CB1120)

1. Create new Purchase Invoice
2. Set `is_return = 1`
3. Set supplier (same as original PI)
4. Do NOT set `return_against` (standalone debit note)
5. Leave items table empty
6. Add one row in Purchase Taxes and Charges:
   - Charge Type: Actual
   - Account Head: COGS or expense account
   - Tax Amount: -2.00
7. Save → should succeed (no MandatoryError)
8. Submit → should succeed

**Expected GL entries**:

| Account | Debit | Credit |
|---------|-------|--------|
| Creditors (payable) | 2.00 | |
| Expense account | | 2.00 |

**Verify**: `frappe.db.get_all("GL Entry", filters={"voucher_no": "<name>", "is_cancelled": 0})`

## Test 2: SI credit note with tax only

Same as Test 1 but for Sales Invoice:
1. Create SI with `is_return = 1`, no items, one Actual tax row
2. Save and submit → should succeed
3. GL entries: debit income, credit receivable

## Test 3: Multi-currency tax-only debit note

**Precondition**: Company with base currency AED, invoice in USD

1. Create PI debit note (is_return=1) in USD
2. No items, one Actual tax: -$2 USD
3. Conversion rate: 3.68
4. Save and submit

**Expected GL entries** (in AED):

| Account | Debit | Credit |
|---------|-------|--------|
| AP USD account | 7.36 | |
| Expense account | | 7.36 |

## Test 4: Debit note with return_against still requires items

1. Create PI with `is_return = 1` and `return_against = <existing PI>`
2. Leave items empty
3. Submit → should fail with "Atleast one item should be entered with negative quantity"

(This preserves existing behavior for linked returns)

## Test 5: Cancel tax-only debit note

1. Submit a tax-only debit note (Test 1)
2. Cancel it
3. Verify reverse GL entries created
4. Verify no errors during cancel

## Test 6: Normal PI still works with items

Regression check: create and submit a normal PI with items and taxes — should work exactly as before.
