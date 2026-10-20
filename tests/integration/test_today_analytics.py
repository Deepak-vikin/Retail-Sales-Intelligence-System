import pytest
from fastapi.testclient import TestClient

from main import app
from app.Services.analytics_service import (
    get_total_bills,
    get_total_revenue,
    get_total_units_sold,
    get_average_bill_value,
    get_today_bills,
    get_today_revenue,
    get_today_units_sold,
    get_today_average_bill_value,
    get_yesterday_bills,
    get_yesterday_revenue,
    get_today_vs_yesterday_comparison,
    get_today_summary,
)

client = TestClient(app)


def test_today_count_differs_from_total_count():
    """Prove that today_count != total_count when historical data exists but today has no data."""
    total_bills = get_total_bills()
    today_bills = get_today_bills()

    # Historical data contains ~72k bills
    assert total_bills > 70000, f"Expected total_bills > 70000, got {total_bills}"
    # Today has no recorded bills
    assert today_bills == 0, f"Expected today_bills == 0, got {today_bills}"
    # Critical invariant: today_bills must NOT equal total_bills
    assert today_bills != total_bills


def test_today_revenue_zero_handling():
    """Verify today's revenue is 0 when no transactions today and does not reflect historical revenue."""
    total_rev = get_total_revenue()
    today_rev = get_today_revenue()

    assert total_rev > 1000000, f"Historical revenue should be > 1M, got {total_rev}"
    assert today_rev == 0.0, f"Today's revenue must be 0.0 when no transactions today, got {today_rev}"
    assert today_rev != total_rev


def test_today_units_sold_zero_handling():
    """Verify today's units sold is 0 when no bills today and does not reflect historical units sold."""
    total_units = get_total_units_sold()
    today_units = get_today_units_sold()

    assert total_units > 100000, f"Historical units should be > 100k, got {total_units}"
    assert today_units == 0, f"Today's units must be 0, got {today_units}"
    assert today_units != total_units


def test_today_average_bill_zero_division_safe():
    """Verify average bill calculation avoids ZeroDivisionError and returns 0.0 when 0 bills."""
    today_avg = get_today_average_bill_value()
    assert today_avg == 0.0, f"Today's average bill should be 0.0 when no bills exist, got {today_avg}"


def test_today_vs_yesterday_comparison_no_fake_trends():
    """Verify yesterday comparison handles 0 transactions properly without fake +8.1% trends."""
    comp = get_today_vs_yesterday_comparison()

    assert comp["today_bills"] == 0
    assert comp["yesterday_bills"] == 0
    # Must NOT produce fake +8.1%, +0%, or -100%
    assert comp["bills_percentage_change"] is None
    assert comp["bills_trend_text"] == "No transactions yesterday"

    assert comp["today_revenue"] == 0.0
    assert comp["yesterday_revenue"] == 0.0
    assert comp["revenue_percentage_change"] is None
    assert comp["revenue_trend_text"] == "No transactions yesterday"


def test_today_summary_service():
    """Verify get_today_summary() returns consistent metrics."""
    summary = get_today_summary()
    assert summary["bills"] == 0
    assert summary["revenue"] == 0.0
    assert summary["units_sold"] == 0
    assert summary["average_bill_value"] == 0.0
    assert "No transactions yesterday" in summary["bills_trend_text"]
    assert "No transactions yesterday" in summary["revenue_trend_text"]


def test_today_api_endpoints():
    """Verify all /analytics/today/* API endpoints return correct date-filtered data."""
    # Today's bills endpoint
    res = client.get("/analytics/today/bills")
    assert res.status_code == 200
    assert res.json() == 0

    # Today's revenue endpoint
    res = client.get("/analytics/today/revenue")
    assert res.status_code == 200
    assert res.json() == 0.0

    # Today's units-sold endpoint
    res = client.get("/analytics/today/units-sold")
    assert res.status_code == 200
    assert res.json() == 0

    # Today's average-bill endpoint
    res = client.get("/analytics/today/average-bill")
    assert res.status_code == 200
    assert res.json() == 0.0

    # Today's comparison endpoint
    res = client.get("/analytics/today/comparison")
    assert res.status_code == 200
    data = res.json()
    assert data["today_bills"] == 0
    assert data["bills_percentage_change"] is None
    assert data["bills_trend_text"] == "No transactions yesterday"

    # Today's summary endpoint
    res = client.get("/analytics/today/summary")
    assert res.status_code == 200
    data = res.json()
    assert data["bills"] == 0
    assert data["revenue"] == 0.0

    # Check that total endpoints still return historical data
    res_total = client.get("/analytics/bills")
    assert res_total.status_code == 200
    assert res_total.json() > 70000

    # Check query param period=today
    res_period = client.get("/analytics/bills?period=today")
    assert res_period.status_code == 200
    assert res_period.json() == 0
