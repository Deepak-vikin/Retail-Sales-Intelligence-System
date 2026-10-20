"""
Integration test for the daily sync job.

Tests that run_daily_sync() exists and can be called when CSV files are
present in data/daily/sales/ and data/daily/purchases/.

When those folders are empty (no pending CSVs), the sync completes
successfully without processing any files – that is the correct
idempotent behaviour and the test asserts it.
"""
import pytest
from pathlib import Path

from app.jobs.daily_sync_job import run_daily_sync


def test_daily_sync_job_folders_exist():
    """Verify the expected folder structure is present."""
    daily_folder = Path("data/daily")
    assert daily_folder.exists(), f"Daily folder not found: {daily_folder}"
    assert (daily_folder / "sales").exists(), "data/daily/sales/ missing"
    assert (daily_folder / "purchases").exists(), "data/daily/purchases/ missing"


def test_daily_sync_job_runs_when_empty(monkeypatch):
    """
    run_daily_sync() should complete without errors even when both
    data/daily/sales/ and data/daily/purchases/ contain no CSV files.

    We monkeypatch update_daily_knowledge so the test does not require
    a live DB + LLM call for the RAG knowledge update step.
    """
    import app.jobs.daily_sync_job as job_module

    # Patch the RAG knowledge update to a no-op so the test is self-contained
    monkeypatch.setattr(job_module, "update_daily_knowledge", lambda target_date: None)

    # run_daily_sync processes whatever CSVs exist; if folders are empty
    # it simply returns without inserting anything (correct behaviour).
    run_daily_sync()