# Invoice Validation Rules

## Date Validation

- All dates must be in ISO 8601 format (`YYYY-MM-DD`)
- Invoice date must be between 2000-01-01 and 2030-12-31
- Due date must be on or after invoice date
- If due date is missing, flag for review but don't fail

## Currency Normalization

- All monetary amounts must be stored as numbers (not strings)
- Currency codes must be ISO 4217 (e.g., USD, EUR, GBP)
- Symbol mapping: `$` → USD, `€` → EUR, `£` → GBP, `¥` → JPY
- If no currency indicator is found, default to USD and flag for review

## Amount Consistency

- `subtotal` + `tax_amount` should equal `total_amount` (within ±0.01 tolerance)
- Sum of all `line_items[].line_total` should equal `subtotal` (within ±0.01)
- All amounts must be non-negative unless document_type is `credit_note`

## Line Item Rules

- Each line item must have at least: `description` and `line_total`
- If `quantity` and `unit_price` are present: `quantity * unit_price` should equal `line_total` (within ±0.01)
- Empty description rows should be skipped (often headers or separators)

## Edge Cases

- **Multi-currency invoices:** If line items are in a different currency than the total, extract both currencies and flag for review
- **Tax-inclusive pricing:** Some invoices show totals inclusive of tax. Check for "Tax Included" or "VAT Inclusive" indicators
- **Rounding differences:** Allow ±0.02 tolerance for invoices with many line items (accumulated rounding)
