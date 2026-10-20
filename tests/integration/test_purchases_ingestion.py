"""
Integration tests – purchase CSV ingestion (sync_purchase_csv).

Strategy
--------
* Tests use pytest's tmp_path to create throwaway CSV files.
* DB connections are mocked so no real data is inserted and the test
  is fully idempotent.
* psycopg2.extras.execute_values() needs cursor.connection.encoding
  to be a real string; the mock cursor sets this to 'UTF8'.
* psycopg2.extras.execute_values() also mogrifies the SQL; the mock
  cursor sets mogrify.return_value to a bytes-like object.
"""
import csv
from unittest.mock import MagicMock, patch

import pytest

from app.ingestion.purchase_sync import sync_purchase_csv


# ---------------------------------------------------------------------------
# Helper: minimal valid purchase CSV content
# ---------------------------------------------------------------------------

VALID_PURCHASE_ROWS = [
    {
        "purchase_id": "800001",
        "product_id": "1",
        "supplier_id": "1",
        "quantity_received": "50",
        "cost_price": "30.00",
        "purchase_date": "2026-10-01",
    },
    {
        "purchase_id": "800002",
        "product_id": "2",
        "supplier_id": "1",
        "quantity_received": "30",
        "cost_price": "75.00",
        "purchase_date": "2026-10-01",
    },
]

FIELDNAMES = [
    "purchase_id",
    "product_id",
    "supplier_id",
    "quantity_received",
    "cost_price",
    "purchase_date",
]


def _write_csv(path, rows, fieldnames=None):
    if fieldnames is None:
        fieldnames = FIELDNAMES
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _make_mock_conn(fetchall_side_effect=None):
    """
    Build a mock psycopg2 connection/cursor that works with
    psycopg2.extras.execute_values().
    """
    cursor = MagicMock()
    cursor.connection.encoding = "UTF8"
    cursor.rowcount = 1
    cursor.mogrify.return_value = b"(mock_values)"

    if fetchall_side_effect is not None:
        cursor.fetchall.side_effect = fetchall_side_effect

    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def valid_purchase_csv(tmp_path):
    """Returns path to a valid purchase CSV file."""
    p = tmp_path / "purchases_test.csv"
    _write_csv(p, VALID_PURCHASE_ROWS)
    return str(p)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_purchase_csv_missing_column_rejected(tmp_path):
    """
    sync_purchase_csv() should raise ValueError when a required column
    is missing from the CSV header.
    """
    p = tmp_path / "bad_header.csv"
    incomplete_rows = [
        {k: v for k, v in row.items() if k != "cost_price"}
        for row in VALID_PURCHASE_ROWS
    ]
    incomplete_fieldnames = [f for f in FIELDNAMES if f != "cost_price"]
    _write_csv(p, incomplete_rows, incomplete_fieldnames)

    with pytest.raises(ValueError, match="cost_price"):
        sync_purchase_csv(str(p))


def test_purchase_csv_empty_rejected(tmp_path):
    """sync_purchase_csv() should raise ValueError when the CSV has no data rows."""
    p = tmp_path / "empty.csv"
    _write_csv(p, [])  # header only

    with pytest.raises(ValueError):
        sync_purchase_csv(str(p))


def test_sync_purchase_csv_inserts_data(valid_purchase_csv):
    """
    sync_purchase_csv() should parse the CSV, verify no duplicates, and
    return a result dict with 'purchases_inserted' and 'inventory_updated'.

    All DB interactions are mocked so no real data is written.
    """
    # fetchall calls inside sync_purchase_csv (in order):
    #   1. SELECT product_id FROM products WHERE product_id = ANY(...)
    #   2. SELECT supplier_id FROM suppliers WHERE supplier_id = ANY(...)
    #   3. SELECT purchase_id FROM purchases WHERE purchase_id = ANY(...)
    mock_conn, mock_cursor = _make_mock_conn(
        fetchall_side_effect=[
            [(1,), (2,)],   # products exist
            [(1,)],         # supplier exists
            [],             # no duplicate purchase_ids
        ]
    )

    with patch("app.ingestion.purchase_sync.connection", return_value=mock_conn):
        result = sync_purchase_csv(valid_purchase_csv)

    assert result is not None
    assert "purchases_inserted" in result
    assert "inventory_updated" in result
    assert result["purchases_inserted"] == 2
    assert result["inventory_updated"] == 2


def test_sync_purchase_csv_rejects_negative_quantity(tmp_path):
    """sync_purchase_csv() should raise ValueError for quantity_received <= 0."""
    p = tmp_path / "bad_quantity.csv"
    bad_rows = [
        {
            "purchase_id": "800099",
            "product_id": "1",
            "supplier_id": "1",
            "quantity_received": "-5",   # invalid
            "cost_price": "30.00",
            "purchase_date": "2026-10-01",
        }
    ]
    _write_csv(p, bad_rows)

    with pytest.raises(ValueError):
        sync_purchase_csv(str(p))