"""
异步任务 API 测试
"""
from pathlib import Path
from unittest.mock import patch
import tempfile

from fastapi.testclient import TestClient

from app.main import app
from app.services.file_registry import FileRecord

client = TestClient(app)


class TestTasksAPI:
    """任务接口测试"""

    def test_create_async_task_passes_rule_codes_for_large_file(self):
        """测试创建大文件任务时透传 rule_codes。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            dxf_path = Path(tmpdir) / "drawing.dxf"
            dxf_path.write_text("fake-dxf")

            dwg_record = FileRecord(
                file_id="dwg-1",
                filename="drawing.dxf",
                file_type="dwg",
                file_path=str(dxf_path),
                suffix=".dxf",
                uploaded_at="2026-03-18T12:00:00",
            )

            fake_task = type("TaskResult", (), {"id": "task-123"})()

            with patch("app.api.v1.tasks.get_uploaded_file", return_value=dwg_record), \
                 patch("app.tasks.review_tasks.process_large_dwg_task.delay", return_value=fake_task) as mock_delay:
                response = client.post("/api/v1/tasks", json={
                    "dwg_file_id": "dwg-1",
                    "rule_codes": ["TEXT_001"],
                    "large_file": True,
                })

            assert response.status_code == 200
            assert response.json()["task_id"] == "task-123"
            kwargs = mock_delay.call_args.kwargs
            assert kwargs["rule_codes"] == ["TEXT_001"]

    def test_get_task_result_prefers_history_storage_record(self):
        """测试任务结果优先读取统一历史存储。"""
        task_result = {
            "task_id": "task-123",
            "record_id": "record-123",
            "status": "SUCCESS",
            "result": {
                "dwg_review": {
                    "overall_score": 60,
                    "assessment": "需修改",
                    "issues": [],
                    "summary": {"total_issues": 0, "by_severity": {}, "by_source": {}, "by_category": {}},
                    "llm_enabled": False,
                }
            },
        }
        stored_result = {
            "dwg_review": {
                "overall_score": 95,
                "assessment": "通过",
                "issues": [],
                "summary": {"total_issues": 0, "by_severity": {}, "by_source": {}, "by_category": {}},
                "llm_enabled": False,
            },
            "dwg_analysis": {
                "file_info": {"dxf_version": "AC1032", "units_name": "米", "filename": "drawing.dxf"},
                "layers": [],
                "blocks": [],
                "statistics": {"layer_count": 0, "block_count": 0, "entity_count": 0, "text_count": 0, "dimension_count": 0, "insert_count": 0},
                "door_window_summary": {"total_doors": 0, "total_windows": 0, "doors": [], "windows": []},
            },
        }

        with patch("app.tasks.review_tasks.get_task_status", return_value={
            "task_id": "task-123",
            "status": "SUCCESS",
            "ready": True,
            "successful": True,
            "failed": False,
            "result": task_result,
        }), patch("app.services.history_storage.get_history_storage") as mock_history:
            mock_history.return_value.get_result.return_value = stored_result
            response = client.get("/api/v1/tasks/task-123/result")

        assert response.status_code == 200
        data = response.json()
        assert data["overall_score"] == 95
        assert data["assessment"] == "通过"
        assert data["dwg_analysis"]["file_info"]["filename"] == "drawing.dxf"
