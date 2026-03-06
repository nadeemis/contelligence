# Invoice Field Mappings

## Mapping Table

| Target Field | Common Variations | Extraction Rule |
|---|---|---|
| `invoice_number` | "Invoice #", "Invoice No.", "Inv. Number", "Reference" | First alphanumeric sequence matching pattern INV-*, #*, or standalone number near "Invoice" header |
| `invoice_date` | "Date", "Invoice Date", "Issued On", "Billing Date" | Date value closest to the invoice number, typically in header area |
| `due_date` | "Due Date", "Payment Due", "Due By", "Net Date" | Date value explicitly labeled as due/payment date |
| `vendor_name` | "From", "Seller", "Billed By", "Company Name" (top of invoice) | Entity name in the "from" or header section |
| `total_amount` | "Total", "Grand Total", "Amount Due", "Balance Due", "Total (USD)" | Largest monetary value at the bottom of the document |
| `currency` | "Currency", "Curr." | ISO 4217 code; infer from currency symbol if not explicit ($ → USD, € → EUR, £ → GBP) |
| `line_items` | Table body rows | Each row: description, quantity, unit_price, line_total |
| `tax_amount` | "Tax", "VAT", "GST", "Sales Tax" | Monetary value labeled with a tax keyword |
| `subtotal` | "Subtotal", "Sub-total", "Net Amount" | Sum before tax |
| `payment_terms` | "Terms", "Payment Terms", "Net 30", "Due on Receipt" | Text near due date or at bottom of invoice |

## Synonym Resolution

When a column header doesn't exactly match, use semantic similarity:
- "Amt" → `amount`
- "Desc." → `description`
- "Qty" → `quantity`
- "U/P" or "Rate" → `unit_price`
