# Documentation Standards

**Version**: 1.0
**Last Updated**: 2026-04-06

This document defines the structure, format, and conventions for all ERPNext customization documentation.

---

## 1. Directory Structure

```
docs/
├── DOCUMENTATION_STANDARDS.md          ← this file
├── INDEX.md                            ← master index
│
├── live/                               ← production features (shipped & in use)
│   ├── tax-only-debit-note/
│   │   ├── technical-guide.md          ← architecture & data flow (developers)
│   │   └── raw/                        ← unedited working docs
│   └── ...
│
├── planned/                            ← features in design or development
│
├── _deprecated/                        ← archived, no longer maintained
```

### Key rules

| File / Folder | Contents | Audience |
|---------------|----------|----------|
| `user-guide.md` | Step-by-step operations manual | End users |
| `technical-guide.md` | Architecture, data flow, field definitions, API reference | Developers |
| `raw/` | Unedited working docs: design docs, test plans, migration notes | Developers |

- Every module folder under `live/` **should** have a `technical-guide.md`.
- `raw/` folders hold original development documents as-is.
- When a `planned/` feature goes live, move its folder to `live/`.

---

## 2. Format Rules

Follow the same conventions as the Next app documentation standards:

| Rule | Details |
|------|---------|
| **Language** | English only. |
| **Heading hierarchy** | `#` title → `##` sections → `###` scenarios. Never skip levels. |
| **UI element names** | Bold — e.g. **Submit**, **Create** |
| **Field names** | Code style — e.g. `is_return`, `item_code` |
| **No raw code** | Explain logic in prose, not by pasting source code. Reference file paths instead. |

---

## 3. Scope

This `docs/` directory covers **customizations made to the ERPNext fork** (`version-14-pps` branch). It does not document standard ERPNext features — only changes and extensions specific to Paysepar's deployment.

### Module Name Mapping

| Folder name | Includes | Key files |
|-------------|----------|-----------|
| `tax-only-debit-note` | Allow PI/SI without items (tax-only debit notes) | `purchase_invoice.json`, `sales_invoice.json`, `taxes_and_totals.py`, `accounts_controller.py`, `sales_and_purchase_return.py` |
