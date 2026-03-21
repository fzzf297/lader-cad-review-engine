"""
从 JSON 文件回填文件元数据和审核历史到数据库
"""
from pathlib import Path

from app.core.config import settings
from app.services.database_gateway import get_database_gateway, run_coro_sync
from app.services.file_registry import get_file_registry
from app.services.history_storage import get_history_storage


def main() -> None:
    gateway = get_database_gateway()
    registry = get_file_registry()
    history = get_history_storage()

    file_records = registry.list()
    review_records, _ = history.list(page=1, page_size=100000)

    imported_files = 0
    imported_reviews = 0

    for record in file_records:
        if run_coro_sync(gateway.upsert_file_record(record)):
            imported_files += 1

    for record in review_records:
        full_record = history.get(record.record_id)
        if full_record and run_coro_sync(gateway.save_review_record(full_record)):
            imported_reviews += 1

    print(f"Imported {imported_files} file records and {imported_reviews} review records into database.")


if __name__ == "__main__":
    main()
