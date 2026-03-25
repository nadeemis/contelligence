---
name: invoice-processing
description: >
  Extracts and validates invoice data from PDF, DOCX, and XLSX files. Handles multi-page invoices, line-item tables, and multi-currency amounts. Use when processing invoices, purchase orders, billing documents, or when the user mentions invoices, POs, or billing.
license: MIT
metadata:
  version: "1.0.0"
  tags: ["finance"]
---

# Invoice Processing

## When to use this Skill

Use this Skill when the user asks to:
- Extract data from invoices (any format)
- Process purchase orders or billing documents
- Build a structured invoice dataset from raw documents
- Validate previously extracted invoice data

## Workflow

Copy this checklist and track your progress:

```
Invoice Processing Progress:
- [ ] Step 1: Discover source files
- [ ] Step 2: Extract content from each file
- [ ] Step 3: Identify and extract invoice fields
- [ ] Step 4: Validate extracted data
- [ ] Step 5: Normalize currency and dates
- [ ] Step 6: Write structured output
- [ ] Step 7: Generate summary report
```

### Step 1: Discover source files

```
Tool: read_blob({ container: "<source>", action: "list", prefix: "*.pdf" })
```

Also check for `.docx` and `.xlsx` files. Invoices may come in any format.

### Step 2: Extract content

Choose tool based on file type:
- PDF with text layer → `extract_pdf` with `extract_tables: true`
- Scanned PDF (no selectable text) → `call_doc_intelligence` with `model: "prebuilt-invoice"`
- DOCX → `extract_docx`
- XLSX → `extract_xlsx`

**Decision rule:** If `extract_pdf` returns empty text but the page count > 0,
the PDF is likely scanned. Switch to `call_doc_intelligence`.

### Step 3: Identify and extract invoice fields

**Required fields:** See [FIELD_MAPPINGS.md](references/FIELD_MAPPINGS.md) for
the complete field mapping table with synonyms and extraction rules.

Core fields to extract:
- Invoice number
- Invoice date
- Due date
- Vendor name
- Vendor address
- Buyer / bill-to name
- Line items (description, quantity, unit price, total)
- Subtotal, tax, total amount
- Currency
- Payment terms

Map fields by **meaning**, not exact header text. "Total Amount", "Grand Total",
"Amount Due", "Invoice Total" all map to `total_amount`.

### Step 4: Validate extracted data

Run the validation script:

```
Tool: run_skill_script({
  skill_name: "invoice-processing",
  script_path: "scripts/validate_invoice.py",
  args: ["<invoice_json_string>"]
})
```

If validation fails, review the error messages and fix the extraction.
Re-validate after fixes.

### Step 5: Normalize currency and dates

- Dates → ISO 8601 (`YYYY-MM-DD`)
- Currency → numeric amount + ISO 4217 currency code
- See [VALIDATION_RULES.md](references/VALIDATION_RULES.md) for edge cases

### Step 6: Write structured output

Write each validated invoice to blob storage:

```
Tool: write_blob({
  container: "agent-outputs",
  path: "invoices/<invoice_number>.json",
  content: <structured_invoice_json>
})
```

Use the schema defined in `assets/output_schema.json` as the target format.
Load it with:

```
Tool: read_skill_file({
  skill_name: "invoice-processing",
  file_path: "assets/output_schema.json"
})
```

### Step 7: Generate summary report

Produce a summary containing:
- Total invoices processed
- Total amount across all invoices (by currency)
- Any invoices that failed validation (with reasons)
- Any invoices flagged for human review

## Edge cases

- **Multi-page invoices:** Line-item tables may span multiple pages. Merge
  table rows across pages before processing.
- **Credit notes:** Negative amounts. Ensure `total_amount` is negative
  and `document_type` is set to `credit_note`.
- **Proforma invoices:** Not final. Set `document_type` to `proforma` and
  flag for review.
- **Missing invoice number:** Generate a synthetic ID from vendor name + date
  and flag for review.
