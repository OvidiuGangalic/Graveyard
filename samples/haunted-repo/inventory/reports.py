import json
from datetime import date


def build_report(rows):
    """Summarise stock rows for the daily report."""
    total = sum(row["quantity"] for row in rows)
    return {"date": date.today().isoformat(), "total": total, "rows": len(rows)}


def export_legacy_csv(rows, path):
    """Old CSV export for the warehouse printer, retired with the printer."""
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("sku,quantity\n")
        for row in rows:
            handle.write(f"{row['sku']},{row['quantity']}\n")
