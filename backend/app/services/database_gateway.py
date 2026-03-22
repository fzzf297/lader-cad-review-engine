"""
数据库网关

以 SQLAlchemy 异步模型为主存储，实现文件元数据和审核历史的数据库读写。
调用方仍可在数据库不可用时回退到 JSON 文件。
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import datetime
import json
import logging
from pathlib import Path
import threading
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from ..db.database import AsyncSessionLocal, init_db
from ..db.models import (
    ContractFile as DbContractFile,
    DWGFile as DbDWGFile,
    FileStatus,
    IssueSource,
    ReviewIssue as DbReviewIssue,
    ReviewRecord as DbReviewRecord,
    SeverityLevel,
)

logger = logging.getLogger(__name__)


def run_coro_sync(coro):
    """在同步上下文中安全执行协程"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: Dict[str, object] = {}
    error: Dict[str, BaseException] = {}

    def runner():
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - defensive
            error["value"] = exc

    thread = threading.Thread(target=runner)
    thread.start()
    thread.join()

    if "value" in error:
        raise error["value"]
    return result.get("value")


class DatabaseGateway:
    """数据库读写网关"""

    def __init__(self):
        self._initialized = False
        self._available = True

    async def _ensure_db(self) -> bool:
        if not self._available:
            return False
        if self._initialized:
            return True
        try:
            await init_db()
            self._initialized = True
            return True
        except Exception as exc:
            logger.warning("数据库初始化不可用，继续使用 JSON 存储: %s", exc)
            self._available = False
            return False

    async def upsert_file_record(self, record) -> bool:
        if not await self._ensure_db():
            return False

        model_cls = DbDWGFile if record.file_type == "dwg" else DbContractFile
        async with AsyncSessionLocal() as session:
            db_record = await session.get(model_cls, record.file_id)
            if db_record is None:
                db_record = model_cls(id=record.file_id, filename=record.filename, original_name=record.filename, file_path=record.file_path)
                session.add(db_record)

            db_record.filename = record.filename
            db_record.original_name = record.filename
            db_record.file_path = record.file_path
            db_record.original_path = record.original_path
            db_record.suffix = record.suffix
            db_record.converted = record.converted
            db_record.file_size = Path(record.file_path).stat().st_size if Path(record.file_path).exists() else 0
            db_record.upload_time = self._parse_datetime(record.uploaded_at)
            if hasattr(db_record, "status"):
                try:
                    db_record.status = FileStatus(record.status)
                except ValueError:
                    db_record.status = FileStatus.UPLOADED

            await session.commit()
        return True

    async def get_file_record(self, file_id: str):
        if not await self._ensure_db():
            return None

        async with AsyncSessionLocal() as session:
            for model_cls, file_type in ((DbDWGFile, "dwg"), (DbContractFile, "contract")):
                db_record = await session.get(model_cls, file_id)
                if db_record is not None:
                    return self._to_file_record(db_record, file_type)
        return None

    async def list_file_records(self, file_type: Optional[str] = None):
        if not await self._ensure_db():
            return None

        records: List[object] = []
        async with AsyncSessionLocal() as session:
            if file_type in (None, "dwg"):
                result = await session.execute(select(DbDWGFile).order_by(DbDWGFile.upload_time.desc()))
                records.extend(self._to_file_record(item, "dwg") for item in result.scalars())
            if file_type in (None, "contract"):
                result = await session.execute(select(DbContractFile).order_by(DbContractFile.upload_time.desc()))
                records.extend(self._to_file_record(item, "contract") for item in result.scalars())

        records.sort(key=lambda record: record.uploaded_at, reverse=True)
        return records

    async def mark_file_consumed(self, file_id: str) -> bool:
        if not await self._ensure_db():
            return False

        async with AsyncSessionLocal() as session:
            for model_cls in (DbDWGFile, DbContractFile):
                db_record = await session.get(model_cls, file_id)
                if db_record is None:
                    continue

                db_record.file_path = ""
                db_record.original_path = None
                db_record.file_size = 0
                if hasattr(db_record, "status"):
                    db_record.status = FileStatus.REVIEWED

                await session.commit()
                return True

        return False

    async def save_review_record(self, record) -> bool:
        if not await self._ensure_db():
            return False

        async with AsyncSessionLocal() as session:
            db_record = await session.get(
                DbReviewRecord,
                record.record_id,
                options=[selectinload(DbReviewRecord.issues)],
            )
            if db_record is None:
                db_record = DbReviewRecord(
                    id=record.record_id,
                    dwg_file_id=record.file_id,
                )
                session.add(db_record)
            else:
                for issue in list(db_record.issues):
                    await session.delete(issue)

            db_record.dwg_file_id = record.file_id
            db_record.review_time = self._parse_datetime(record.created_at)
            db_record.overall_score = record.overall_score
            db_record.assessment = record.assessment
            db_record.enable_llm = record.enable_llm
            db_record.result_json = json.dumps(record.result, ensure_ascii=False)

            for issue in record.result.get("dwg_review", {}).get("issues", []):
                db_issue = DbReviewIssue(
                    category=issue.get("category", ""),
                    severity=self._to_severity(issue.get("severity", "warning")),
                    description=issue.get("description", ""),
                    location=issue.get("location", ""),
                    suggestion=issue.get("suggestion", ""),
                    source=self._to_issue_source(issue.get("source", "rule")),
                    confidence=issue.get("confidence", 1.0),
                )
                db_record.issues.append(db_issue)

            await session.commit()
        return True

    async def get_review_record(self, record_id: str):
        if not await self._ensure_db():
            return None

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(DbReviewRecord)
                .options(selectinload(DbReviewRecord.dwg_file), selectinload(DbReviewRecord.issues))
                .where(DbReviewRecord.id == record_id)
            )
            db_record = result.scalar_one_or_none()
            if db_record is None:
                return None
            return self._to_review_record(db_record)

    async def get_review_result(self, record_id: str) -> Optional[Dict]:
        record = await self.get_review_record(record_id)
        return record.result if record else None

    async def list_review_records(
        self,
        page: int = 1,
        page_size: int = 20,
        file_type: Optional[str] = None,
        assessment: Optional[str] = None,
    ) -> Optional[Tuple[List[object], int]]:
        if not await self._ensure_db():
            return None

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(DbReviewRecord)
                .options(selectinload(DbReviewRecord.dwg_file), selectinload(DbReviewRecord.issues))
                .order_by(DbReviewRecord.review_time.desc())
            )
            records = [self._to_review_record(item) for item in result.scalars()]

        if file_type:
            records = [record for record in records if record.file_type == file_type]
        if assessment:
            records = [record for record in records if record.assessment == assessment]

        total = len(records)
        start = (page - 1) * page_size
        end = start + page_size
        return records[start:end], total

    async def delete_review_record(self, record_id: str) -> Optional[bool]:
        if not await self._ensure_db():
            return None

        async with AsyncSessionLocal() as session:
            db_record = await session.get(DbReviewRecord, record_id)
            if db_record is None:
                return False
            await session.delete(db_record)
            await session.commit()
        return True

    async def get_review_statistics(self) -> Optional[Dict]:
        listed = await self.list_review_records(page=1, page_size=100000)
        if listed is None:
            return None
        records, _ = listed
        if not records:
            return {
                "total_reviews": 0,
                "avg_score": 0,
                "by_assessment": {},
                "by_file_type": {},
            }

        by_assessment: Dict[str, int] = {}
        by_file_type: Dict[str, int] = {}
        for record in records:
            by_assessment[record.assessment] = by_assessment.get(record.assessment, 0) + 1
            by_file_type[record.file_type] = by_file_type.get(record.file_type, 0) + 1

        avg_score = sum(record.overall_score for record in records) / len(records)
        return {
            "total_reviews": len(records),
            "avg_score": round(avg_score, 1),
            "by_assessment": by_assessment,
            "by_file_type": by_file_type,
        }

    def _to_file_record(self, db_record, file_type: str):
        from .file_registry import FileRecord

        return FileRecord(
            file_id=db_record.id,
            filename=db_record.filename,
            file_type=file_type,
            file_path=db_record.file_path,
            original_path=getattr(db_record, "original_path", None),
            suffix=getattr(db_record, "suffix", "") or "",
            status=getattr(getattr(db_record, "status", None), "value", "uploaded"),
            converted=getattr(db_record, "converted", False),
            uploaded_at=db_record.upload_time.isoformat() if db_record.upload_time else datetime.now().isoformat(),
        )

    def _to_review_record(self, db_record: DbReviewRecord):
        from .history_storage import ReviewRecord

        result = json.loads(db_record.result_json or "{}")
        return ReviewRecord(
            record_id=db_record.id,
            file_id=db_record.dwg_file_id,
            file_name=db_record.dwg_file.filename if db_record.dwg_file else "",
            file_type="dwg",
            created_at=db_record.review_time.isoformat() if db_record.review_time else datetime.now().isoformat(),
            overall_score=db_record.overall_score,
            assessment=db_record.assessment,
            issue_count=len(db_record.issues),
            enable_llm=db_record.enable_llm,
            result=result,
        )

    def _parse_datetime(self, value: str) -> datetime:
        try:
            return datetime.fromisoformat(value)
        except Exception:
            return datetime.utcnow()

    def _to_severity(self, value: str) -> SeverityLevel:
        try:
            return SeverityLevel(value)
        except ValueError:
            return SeverityLevel.WARNING

    def _to_issue_source(self, value: str) -> IssueSource:
        try:
            return IssueSource(value)
        except ValueError:
            return IssueSource.RULE


_database_gateway: Optional[DatabaseGateway] = None


def get_database_gateway() -> DatabaseGateway:
    global _database_gateway
    if _database_gateway is None:
        _database_gateway = DatabaseGateway()
    return _database_gateway
