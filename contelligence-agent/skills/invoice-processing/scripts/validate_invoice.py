#!/usr/bin/env python3
"""Validate extracted invoice data against business rules."""

import json
import sys
from datetime import datetime


def validate(invoice: dict) -> list[dict]:
    """Return a list of validation issues (empty = valid)."""
    issues = []

    # Required fields
    required = ["invoice_number", "invoice_date", "vendor_name", "total_amount"]
    for field in required:
        if not invoice.get(field):
            issues.append({
                "severity": "critical",
                "field": field,
                "message": f"Required field '{field}' is missing or empty",
            })

    # Date validation
    for date_field in ["invoice_date", "due_date"]:
        val = invoice.get(date_field)
        if val:
            try:
                dt = datetime.fromisoformat(val)
                if dt.year < 2000 or dt.year > 2030:
                    issues.append({
                        "severity": "warning",
                        "field": date_field,
                        "message": f"Date {val} is outside expected range (2000-2030)",
                    })
            except ValueError:
                issues.append({
                    "severity": "critical",
                    "field": date_field,
                    "message": f"Invalid date format: '{val}'. Expected ISO 8601.",
                })

    # Amount validation
    total = invoice.get("total_amount")
    if total is not None:
        try:
            amount = float(total)
            if amount == 0:
                issues.append({
                    "severity": "warning",
                    "field": "total_amount",
                    "message": "Total amount is zero — verify this is correct",
                })
        except (ValueError, TypeError):
            issues.append({
                "severity": "critical",
                "field": "total_amount",
                "message": f"Cannot parse total_amount: '{total}'",
            })

    # Line item consistency
    line_items = invoice.get("line_items", [])
    if line_items:
        computed_subtotal = sum(
            float(item.get("line_total", 0)) for item in line_items
        )
        reported_subtotal = float(invoice.get("subtotal", 0) or 0)
        if reported_subtotal and abs(computed_subtotal - reported_subtotal) > 0.01:
            issues.append({
                "severity": "warning",
                "field": "subtotal",
                "message": (
                    f"Line item sum ({computed_subtotal:.2f}) differs from "
                    f"reported subtotal ({reported_subtotal:.2f})"
                ),
            })

    return issues


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: validate_invoice.py '<json_string>'"}))
        sys.exit(1)

    try:
        invoice_data = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON: {e}"}))
        sys.exit(1)

    issues = validate(invoice_data)
    print(json.dumps({
        "valid": len(issues) == 0,
        "issues": issues,
        "checked_fields": ["invoice_number", "invoice_date", "due_date",
                           "vendor_name", "total_amount", "line_items", "subtotal"],
    }))
