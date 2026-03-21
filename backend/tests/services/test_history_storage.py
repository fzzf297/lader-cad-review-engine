"""
历史记录存储测试
"""
import pytest
import tempfile
import os
from pathlib import Path
from datetime import datetime

from app.services.history_storage import (
    HistoryStorage, ReviewRecord, get_history_storage
)


class TestReviewRecord:
    """审核记录测试"""

    def test_create_review_record(self):
        """测试创建审核记录"""
        record = ReviewRecord(
            record_id="test-123",
            file_id="file-456",
            file_name="test.dwg",
            file_type="dwg",
            created_at="2024-01-01T12:00:00",
            overall_score=85.5,
            assessment="通过",
            issue_count=2,
            enable_llm=True,
            result={"test": "data"}
        )

        assert record.record_id == "test-123"
        assert record.file_id == "file-456"
        assert record.file_name == "test.dwg"
        assert record.file_type == "dwg"
        assert record.overall_score == 85.5
        assert record.assessment == "通过"
        assert record.issue_count == 2
        assert record.enable_llm is True
        assert record.result == {"test": "data"}

    def test_review_record_defaults(self):
        """测试审核记录默认值"""
        record = ReviewRecord(
            record_id="test",
            file_id="file",
            file_name="test.dwg",
            file_type="dwg",
            created_at="2024-01-01",
            overall_score=0,
            assessment="",
            issue_count=0
        )

        assert record.enable_llm is False
        assert record.contract_file_id is None
        assert record.contract_file_name is None
        assert record.result == {}

    def test_review_record_with_contract(self):
        """测试包含合同的审核记录"""
        record = ReviewRecord(
            record_id="test",
            file_id="file",
            file_name="project.dwg",
            file_type="dwg",
            created_at="2024-01-01",
            overall_score=90,
            assessment="通过",
            issue_count=0,
            contract_file_id="contract-123",
            contract_file_name="合同.docx"
        )

        assert record.contract_file_id == "contract-123"
        assert record.contract_file_name == "合同.docx"


class TestHistoryStorage:
    """历史记录存储测试"""

    def setup_method(self):
        """每个测试方法前创建临时目录"""
        self.temp_dir = tempfile.mkdtemp()
        self.storage = HistoryStorage(self.temp_dir)

    def teardown_method(self):
        """每个测试方法后清理"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_save_and_get_record(self):
        """测试保存和获取记录"""
        record = ReviewRecord(
            record_id="save-test",
            file_id="file-1",
            file_name="test.dwg",
            file_type="dwg",
            created_at=datetime.now().isoformat(),
            overall_score=85,
            assessment="通过",
            issue_count=1,
            result={"dwg_review": {"overall_score": 85}}
        )

        # 保存
        success = self.storage.save(record)
        assert success is True

        # 获取
        retrieved = self.storage.get("save-test")
        assert retrieved is not None
        assert retrieved.record_id == "save-test"
        assert retrieved.file_name == "test.dwg"
        assert retrieved.overall_score == 85

    def test_get_result(self):
        """测试获取审核结果"""
        record = ReviewRecord(
            record_id="result-test",
            file_id="file-2",
            file_name="result.dwg",
            file_type="dwg",
            created_at=datetime.now().isoformat(),
            overall_score=90,
            assessment="通过",
            issue_count=0,
            result={"dwg_review": {"overall_score": 90, "issues": []}}
        )

        self.storage.save(record)

        # 获取结果
        result = self.storage.get_result("result-test")
        assert result is not None
        assert result["dwg_review"]["overall_score"] == 90

    def test_get_nonexistent_record(self):
        """测试获取不存在的记录"""
        record = self.storage.get("nonexistent")
        assert record is None

        result = self.storage.get_result("nonexistent")
        assert result is None

    def test_list_records(self):
        """测试列出记录"""
        # 添加多条记录
        for i in range(5):
            record = ReviewRecord(
                record_id=f"list-test-{i}",
                file_id=f"file-{i}",
                file_name=f"test{i}.dwg",
                file_type="dwg",
                created_at=datetime.now().isoformat(),
                overall_score=80 + i,
                assessment="通过" if i < 3 else "需修改",
                issue_count=i
            )
            self.storage.save(record)

        # 获取列表
        records, total = self.storage.list(page=1, page_size=3)

        assert total == 5
        assert len(records) == 3

        # 第二页
        records2, _ = self.storage.list(page=2, page_size=3)
        assert len(records2) == 2

    def test_list_with_filter(self):
        """测试带筛选的列表"""
        # 添加不同类型的记录
        self.storage.save(ReviewRecord(
            record_id="filter-1",
            file_id="f1",
            file_name="test1.dwg",
            file_type="dwg",
            created_at=datetime.now().isoformat(),
            overall_score=90,
            assessment="通过",
            issue_count=0
        ))

        self.storage.save(ReviewRecord(
            record_id="filter-2",
            file_id="f2",
            file_name="contract.docx",
            file_type="contract",
            created_at=datetime.now().isoformat(),
            overall_score=80,
            assessment="需修改",
            issue_count=1
        ))

        # 按文件类型筛选
        records, total = self.storage.list(file_type="dwg")
        assert total == 2
        assert records[0].file_type == "dwg"

        # 按审核结论筛选
        records, total = self.storage.list(assessment="需修改")
        assert total == 1
        assert records[0].assessment == "需修改"

    def test_delete_record(self):
        """测试删除记录"""
        record = ReviewRecord(
            record_id="delete-test",
            file_id="file-del",
            file_name="delete.dwg",
            file_type="dwg",
            created_at=datetime.now().isoformat(),
            overall_score=85,
            assessment="通过",
            issue_count=0
        )

        self.storage.save(record)

        # 删除
        success = self.storage.delete("delete-test")
        assert success is True

        # 确认已删除
        retrieved = self.storage.get("delete-test")
        assert retrieved is None

    def test_delete_nonexistent(self):
        """测试删除不存在的记录"""
        success = self.storage.delete("nonexistent")
        assert success is False

    def test_get_statistics(self):
        """测试获取统计信息"""
        # 添加多条记录
        self.storage.save(ReviewRecord(
            record_id="stat-1",
            file_id="s1",
            file_name="test1.dwg",
            file_type="dwg",
            created_at=datetime.now().isoformat(),
            overall_score=90,
            assessment="通过",
            issue_count=0
        ))

        self.storage.save(ReviewRecord(
            record_id="stat-2",
            file_id="s2",
            file_name="test2.dwg",
            file_type="dwg",
            created_at=datetime.now().isoformat(),
            overall_score=70,
            assessment="需修改",
            issue_count=2
        ))

        self.storage.save(ReviewRecord(
            record_id="stat-3",
            file_id="s3",
            file_name="test3.dwg",
            file_type="dwg",
            created_at=datetime.now().isoformat(),
            overall_score=80,
            assessment="通过",
            issue_count=1
        ))

        stats = self.storage.get_statistics()

        assert stats["total_reviews"] == 3
        assert stats["avg_score"] == 80  # (90+70+80)/3
        assert stats["by_assessment"]["通过"] == 2
        assert stats["by_assessment"]["需修改"] == 1

    def test_get_statistics_empty(self):
        """测试空存储的统计信息"""
        stats = self.storage.get_statistics()

        assert stats["total_reviews"] == 0
        assert stats["avg_score"] == 0
        assert stats["by_assessment"] == {}
        assert stats["by_file_type"] == {}

    def test_persistence(self):
        """测试持久化"""
        # 保存记录
        record = ReviewRecord(
            record_id="persist-test",
            file_id="file-p",
            file_name="persist.dwg",
            file_type="dwg",
            created_at=datetime.now().isoformat(),
            overall_score=85,
            assessment="通过",
            issue_count=0,
            result={"test": "persist"}
        )

        self.storage.save(record)

        # 创建新的存储实例（模拟重启）
        new_storage = HistoryStorage(self.temp_dir)

        # 验证数据仍然存在
        retrieved = new_storage.get("persist-test")
        assert retrieved is not None
        assert retrieved.file_name == "persist.dwg"


class TestGetHistoryStorage:
    """全局存储实例测试"""

    def test_singleton_pattern(self):
        """测试单例模式"""
        # 注意：这个测试可能会影响其他测试，因为全局状态
        # 这里只是验证函数存在且可调用
        from app.services import history_storage

        # 重置全局实例
        history_storage._history_storage = None

        # 获取实例
        storage1 = get_history_storage()
        storage2 = get_history_storage()

        assert storage1 is storage2
