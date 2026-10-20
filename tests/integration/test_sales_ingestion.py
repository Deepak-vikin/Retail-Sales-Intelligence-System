"""
Integration tests – sales CSV ingestion (sync_daily_csv).

Strategy
--------
* Tests use pytest's tmp_path to create throwaway CSV files.
* The database connections used by sync_daily_csv and csv_validator are
  patched so that no real data is written to the production database.
* psycopg2.extras.execute_values() looks up cursor.connection.encoding
  to encode the SQL; the mock cursor must expose this as a real string.
* We test: valid CSV passes validation, invalid CSV is rejected, and
  the result dict from sync_daily_csv has the correct structure.
"""
import csv
from unittest.mock import MagicMock, patch

import pytest

from app.ingestion.daily_sync import sync_daily_csv
from app.ingestion.csv_validator import validate_csv


# ---------------------------------------------------------------------------
# Helper: minimal valid sales CSV content
# ---------------------------------------------------------------------------

VALID_SALES_ROWS = [
    {
        "bill_id": "900001",
        "cashier_id": "1",
        "transaction_datetime": "2026-10-01T10:00:00",
        "payment_mode": "Cash",
        "product_id": "1",
        "quantity": "2",
        "unit_price": "50.00",
        "discount": "0",
    },
    {
        "bill_id": "900001",
        "cashier_id": "1",
        "transaction_datetime": "2026-10-01T10:00:00",
        "payment_mode": "Cash",
        "product_id": "2",
        "quantity": "1",
        "unit_price": "100.00",
        "discount": "5.00",
    },
]

FIELDNAMES = [
    "bill_id",
    "cashier_id",
    "transaction_datetime",
    "payment_mode",
    "product_id",
    "quantity",
    "unit_price",
    "discount",
]


def _write_csv(path, rows, fieldnames=None):
    if fieldnames is None:
        fieldnames = FIELDNAMES
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _make_mock_conn(fetchall_side_effect=None, fetchone_return=None):
    """
    Build a mock psycopg2 connection/cursor pair that works with
    psycopg2.extras.execute_values().

    execute_values() calls  cur.connection.encoding  to encode the SQL
    string, so we must set that to a real str value ('UTF8').
    """
    cursor = MagicMock()
    # execute_values encodes the SQL using cursor.connection.encoding
    cursor.connection.encoding = "UTF8"
    cursor.rowcount = 1
    cursor.mogrify.return_value = b"(mock_values)"

    if fetchall_side_effect is not None:
        cursor.fetchall.side_effect = fetchall_side_effect
    if fetchone_return is not None:
        cursor.fetchone.return_value = fetchone_return

    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def valid_sales_csv(tmp_path):
    """Returns path to a valid sales CSV file."""
    p = tmp_path / "sales_test.csv"
    _write_csv(p, VALID_SALES_ROWS)
    return str(p)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_sales_csv_valid_passes_validator(valid_sales_csv):
    """
    validate_csv() should return an empty error list for a well-formed CSV.
    The DB call inside csv_validator (product lookup) is mocked.
    """
    mock_conn, mock_cursor = _make_mock_conn(
        fetchall_side_effect=[[(1,), (2,)]]
    )
    with patch("app.ingestion.csv_validator.connection", return_value=mock_conn):
        errors = validate_csv(valid_sales_csv)

    assert errors == [], f"Expected no errors, got: {errors}"


def test_sales_csv_missing_column_rejected(tmp_path):
    """validate_csv() should report a missing-column error."""
    p = tmp_path / "bad_header.csv"
    incomplete_rows = [
        {k: v for k, v in row.items() if k != "discount"}
        for row in VALID_SALES_ROWS
    ]
    incomplete_fieldnames = [f for f in FIELDNAMES if f != "discount"]
    _write_csv(p, incomplete_rows, incomplete_fieldnames)

    # Missing-column check runs before the DB query; no patch needed
    errors = validate_csv(str(p))
    assert any("discount" in e.lower() or "missing" in e.lower() for e in errors), (
        f"Expected missing-column error, got: {errors}"
    )


def test_sync_daily_csv_inserts_data(valid_sales_csv):
    """
    sync_daily_csv() should parse the CSV, detect no duplicates, and
    return a result dict with the expected keys.

    Both connections (csv_validator and daily_sync) are mocked so no
    real data is written.
    """
    # --- csv_validator connection (product lookup) ---
    validator_conn, validator_cursor = _make_mock_conn(
        fetchall_side_effect=[[(1,), (2,)]]
    )

    # --- daily_sync connection ---
    # fetchall calls in order:
    #   1. SELECT bill_id FROM bills WHERE bill_id = ANY(...)  -> [] (no duplicates)
    # fetchone calls in order:
    #   1. SELECT COALESCE(MAX(item_id), 0) + 1 FROM bill_items -> (1000,)
    sync_conn, sync_cursor = _make_mock_conn(
        fetchall_side_effect=[[]],   # no existing bill_ids
        fetchone_return=(1000,),     # next item_id
    )

    with patch("app.ingestion.csv_validator.connection", return_value=validator_conn):
        with patch("app.ingestion.daily_sync.connection", return_value=sync_conn):
            result = sync_daily_csv(valid_sales_csv)

    assert result is not None
    assert "bills_inserted" in result
    assert "bill_items_inserted" in result
    assert result["bills_inserted"] == 1
    assert result["bill_items_inserted"] == 2


def test_sync_daily_csv_rejects_empty_csv(tmp_path):
    """sync_daily_csv() should raise ValueError for a header-only CSV."""
    p = tmp_path / "empty.csv"
    _write_csv(p, [])  # header only, no data rows

    mock_conn, mock_cursor = _make_mock_conn(
        fetchall_side_effect=[[(1,), (2,)]]
    )
    with patch("app.ingestion.csv_validator.connection", return_value=mock_conn):
        with pytest.raises(ValueError):
            sync_daily_csv(str(p))