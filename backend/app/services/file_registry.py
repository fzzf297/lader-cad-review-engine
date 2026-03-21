"""
上传文件注册表服务

将上传文件元数据持久化到 ${UPLOAD_DIR}/index.json，
避免依赖进程内存中的共享字典。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from ..core.config import settings
from .database_gateway import get_database_gateway, run_coro_sync

logger = logging.getLogger(__name__)


@dataclass
class FileRecord:
    """上传文件元数据"""

    file_id: str
    filename: str
    file_type: str
    file_path: str
    original_path: Optional[str] = None
    suffix: str = ""
    status: str = "uploaded"
    converted: bool = False
    uploaded_at: str = field(default_factory=lambda: datetime.now().isoformat())


class FileRegistry:
    """基于 JSON 文件的上传文件注册表"""

    def __init__(self, storage_path: Optional[str] = None):
        base_dir = Path(settings.UPLOAD_DIR)
        self.storage_path = Path(storage_path) if storage_path else base_dir / "index.json"
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._records: Dict[str, FileRecord] = {}
        self._load()

    def _load(self) -> None:
        """加载已有元数据"""
        if not self.storage_path.exists():
            return

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            logger.error("加载文件注册表失败: %s", exc)
            return

        items = data.values() if isinstance(data, dict) else data
        for item in items:
            if "file_id" not in item:
                continue
            try:
                record = FileRecord(**item)
            except TypeError as exc:
                logger.warning("跳过无法解析的文件注册项 %s: %s", item, exc)
                continue
            self._records[record.file_id] = record

    def _save(self) -> None:
        """保存当前元数据"""
        data = [asdict(record) for record in self.list()]
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def register(self, record: FileRecord) -> FileRecord:
        """注册或更新文件元数据"""
        self._records[record.file_id] = record
        self._save()
        try:
            run_coro_sync(get_database_gateway().upsert_file_record(record))
        except Exception as exc:
            logger.warning("同步文件元数据到数据库失败，继续使用 JSON 存储: %s", exc)
        return record

    def get(self, file_id: str) -> Optional[FileRecord]:
        """根据 file_id 获取文件元数据"""
        try:
            db_record = run_coro_sync(get_database_gateway().get_file_record(file_id))
            if db_record is not None:
                return db_record
        except Exception as exc:
            logger.warning("从数据库读取文件元数据失败，回退到 JSON: %s", exc)
        return self._records.get(file_id)

    def list(self, file_type: Optional[str] = None) -> List[FileRecord]:
        """列出文件，默认按上传时间倒序"""
        try:
            db_records = run_coro_sync(get_database_gateway().list_file_records(file_type=file_type))
            if db_records:
                return db_records
        except Exception as exc:
            logger.warning("从数据库列出文件失败，回退到 JSON: %s", exc)

        records = list(self._records.values())
        if file_type:
            records = [record for record in records if record.file_type == file_type]
        records.sort(key=lambda record: record.uploaded_at, reverse=True)
        return records


_file_registry: Optional[FileRegistry] = None


def get_file_registry(storage_path: Optional[str] = None) -> FileRegistry:
    """获取文件注册表实例"""
    if storage_path is not None:
        return FileRegistry(storage_path=storage_path)

    global _file_registry
    if _file_registry is None:
        _file_registry = FileRegistry()
    return _file_registry
