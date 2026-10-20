import os
import shutil
from datetime import date

from app.ingestion.daily_sync import sync_daily_csv
from app.ingestion.purchase_sync import sync_purchase_csv
from app.rag.knowledge_generator import generate_daily_knowledge
from app.rag.vector_store import upsert_document


def update_daily_knowledge(target_date):
    document = generate_daily_knowledge(target_date)

    result = upsert_document(
        content=document,
        metadata={
            "type": "daily_retail_summary",
            "date": str(target_date),
        },
    )

    print(
        f"RAG knowledge {result['action']}: "
        f"document_id={result['id']}"
    )


def process_folder(
    source_folder,
    processed_folder,
    rejected_folder,
    sync_function,
):
    os.makedirs(source_folder, exist_ok=True)
    os.makedirs(processed_folder, exist_ok=True)
    os.makedirs(rejected_folder, exist_ok=True)

    for file_name in sorted(os.listdir(source_folder)):

        if not file_name.lower().endswith(".csv"):
            continue

        file_path = os.path.join(source_folder, file_name)

        try:
            result = sync_function(file_path)

            shutil.move(
                file_path,
                os.path.join(processed_folder, file_name),
            )

            print(f"Processed: {file_name}")
            print(f"Result: {result}")

        except Exception as error:

            shutil.move(
                file_path,
                os.path.join(rejected_folder, file_name),
            )

            print(
                f"Rejected: {file_name} -> {error}"
            )


def run_daily_sync():

    today = date.today()

    process_folder(
        "data/daily/sales",
        "data/processed/sales",
        "data/rejected/sales",
        sync_daily_csv,
    )

    process_folder(
        "data/daily/purchases",
        "data/processed/purchases",
        "data/rejected/purchases",
        sync_purchase_csv,
    )

    update_daily_knowledge(today)

    print("Daily sync completed.")