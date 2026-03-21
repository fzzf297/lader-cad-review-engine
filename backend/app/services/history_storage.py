"""
历史记录存储服务 - 审核记录持久化
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
import json
import logging
from pathlib import Path

from .database_gateway import get_database_gateway, run_coro_sync

logger = logging.getLogger(__name__)


@dataclass
class ReviewRecord:
    """审核记录"""
    record_id: str
    file_id: str
    file_name: str
    file_type: str  # dwg / contract
    created_at: str
    overall_score: float
    assessment: str
    issue_count: int
    enable_llm: bool = False
    result: Dict[str, Any] = field(default_factory=dict)


class HistoryStorage:
    """历史记录存储（生产环境应使用数据库）"""

    def __init__(self, storage_dir: str = None):
        if storage_dir:
            self.storage_dir = Path(storage_dir)
        else:
            self.storage_dir = Path(__file__).parent.parent.parent / "data" / "history"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # 内存缓存
        self._records: Dict[str, ReviewRecord] = {}
        self._load_records()

    def _load_records(self):
        """加载已有记录"""
        index_file = self.storage_dir / "index.json"
        if index_file.exists():
            try:
                with open(index_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        item.pop("contract_file_id", None)
                        item.pop("contract_file_name", None)
                        record = ReviewRecord(**item)
                        self._records[record.record_id] = record
                logger.info(f"加载了 {len(self._records)} 条历史记录")
            except Exception as e:
                logger.error(f"加载历史记录失败: {e}")

    def _save_index(self):
        """保存索引文件"""
        index_file = self.storage_dir / "index.json"
        try:
            data = [self._sanitize_json(asdict(r)) for r in self._records.values()]
            with open(index_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存历史记录索引失败: {e}")

    def save(self, record: ReviewRecord) -> bool:
        """保存审核记录"""
        try:
            # 保存完整结果到单独文件
            result_file = self.storage_dir / f"{record.record_id}.json"
            with open(result_file, "w", encoding="utf-8") as f:
                json.dump(self._sanitize_json(record.result), f, ensure_ascii=False, indent=2)

            # 清空结果以减少内存占用（结果已保存到文件）
            record_to_store = ReviewRecord(
                record_id=record.record_id,
                file_id=record.file_id,
                file_name=record.file_name,
                file_type=record.file_type,
                created_at=record.created_at,
                overall_score=record.overall_score,
                assessment=record.assessment,
                issue_count=record.issue_count,
                enable_llm=record.enable_llm,
                result={}  # 结果单独存储
            )

            # 保存到内存和索引
            self._records[record.record_id] = record_to_store
            self._save_index()

            try:
                run_coro_sync(get_database_gateway().save_review_record(record))
            except Exception as db_exc:
                logger.warning(f"同步审核记录到数据库失败，继续保留 JSON 存储: {db_exc}")

            logger.info(f"保存审核记录: {record.record_id}")
            return True
        except Exception as e:
            logger.error(f"保存审核记录失败: {e}")
            return False

    def _sanitize_json(self, value: Any) -> Any:
        if isinstance(value, str):
            return value.encode("utf-8", errors="ignore").decode("utf-8")
        if isinstance(value, list):
            return [self._sanitize_json(item) for item in value]
        if isinstance(value, dict):
            return {
                self._sanitize_json(key): self._sanitize_json(item)
                for key, item in value.items()
            }
        return value

    def get(self, record_id: str) -> Optional[ReviewRecord]:
        """获取审核记录"""
        try:
            db_record = run_coro_sync(get_database_gateway().get_review_record(record_id))
            if db_record is not None:
                return db_record
        except Exception as db_exc:
            logger.warning(f"从数据库获取审核记录失败，回退到 JSON: {db_exc}")

        record = self._records.get(record_id)
        if record:
            # 加载完整结果
            result_file = self.storage_dir / f"{record_id}.json"
            if result_file.exists():
                try:
                    with open(result_file, "r", encoding="utf-8") as f:
                        record.result = json.load(f)
                except Exception as e:
                    logger.error(f"加载审核结果失败: {e}")
        return record

    def get_result(self, record_id: str) -> Optional[Dict[str, Any]]:
        """获取审核结果"""
        try:
            db_result = run_coro_sync(get_database_gateway().get_review_result(record_id))
            if db_result is not None:
                return db_result
        except Exception as db_exc:
            logger.warning(f"从数据库获取审核结果失败，回退到 JSON: {db_exc}")

        result_file = self.storage_dir / f"{record_id}.json"
        if result_file.exists():
            try:
                with open(result_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载审核结果失败: {e}")
        return None

    def list(
        self,
        page: int = 1,
        page_size: int = 20,
        file_type: Optional[str] = None,
        assessment: Optional[str] = None
    ) -> tuple[List[ReviewRecord], int]:
        """获取审核记录列表（分页）"""
        try:
            db_listed = run_coro_sync(
                get_database_gateway().list_review_records(
                    page=page,
                    page_size=page_size,
                    file_type=file_type,
                    assessment=assessment,
                )
            )
            if db_listed is not None:
                db_records, db_total = db_listed
                if db_records or not self._records:
                    return db_records, db_total
        except Exception as db_exc:
            logger.warning(f"从数据库列出审核记录失败，回退到 JSON: {db_exc}")

        records = list(self._records.values())

        # 筛选
        if file_type:
            records = [r for r in records if r.file_type == file_type]
        if assessment:
            records = [r for r in records if r.assessment == assessment]

        # 排序（最新在前）
        records.sort(key=lambda x: x.created_at, reverse=True)

        # 分页
        total = len(records)
        start = (page - 1) * page_size
        end = start + page_size
        return records[start:end], total

    def delete(self, record_id: str) -> bool:
        """删除审核记录"""
        if record_id not in self._records:
            try:
                db_deleted = run_coro_sync(get_database_gateway().delete_review_record(record_id))
                if db_deleted is not None:
                    return db_deleted
            except Exception as db_exc:
                logger.warning(f"从数据库删除审核记录失败，回退到 JSON: {db_exc}")
            return False

        try:
            # 删除结果文件
            result_file = self.storage_dir / f"{record_id}.json"
            if result_file.exists():
                result_file.unlink()

            # 从内存和索引中删除
            del self._records[record_id]
            self._save_index()

            try:
                run_coro_sync(get_database_gateway().delete_review_record(record_id))
            except Exception as db_exc:
                logger.warning(f"从数据库删除审核记录失败，JSON 记录已删除: {db_exc}")

            logger.info(f"删除审核记录: {record_id}")
            return True
        except Exception as e:
            logger.error(f"删除审核记录失败: {e}")
            return False

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        try:
            db_stats = run_coro_sync(get_database_gateway().get_review_statistics())
            if db_stats is not None and (db_stats["total_reviews"] > 0 or not self._records):
                return db_stats
        except Exception as db_exc:
            logger.warning(f"从数据库获取统计信息失败，回退到 JSON: {db_exc}")

        records = list(self._records.values())

        if not records:
            return {
                "total_reviews": 0,
                "avg_score": 0,
                "by_assessment": {},
                "by_file_type": {}
            }

        # 按审核结论统计
        by_assessment = {}
        for r in records:
            by_assessment[r.assessment] = by_assessment.get(r.assessment, 0) + 1

        # 按文件类型统计
        by_file_type = {}
        for r in records:
            by_file_type[r.file_type] = by_file_type.get(r.file_type, 0) + 1

        # 平均分数
        avg_score = sum(r.overall_score for r in records) / len(records)

        return {
            "total_reviews": len(records),
            "avg_score": round(avg_score, 1),
            "by_assessment": by_assessment,
            "by_file_type": by_file_type
        }


# 全局存储实例
_history_storage: Optional[HistoryStorage] = None


def get_history_storage() -> HistoryStorage:
    """获取历史记录存储实例"""
    global _history_storage
    if _history_storage is None:
        from ..core.config import settings
        storage_dir = Path(settings.UPLOAD_DIR) / "history"
        _history_storage = HistoryStorage(str(storage_dir))
    return _history_storage
