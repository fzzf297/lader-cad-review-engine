"""
审核 API 测试
"""
from pathlib import Path
from unittest.mock import AsyncMock, patch
import tempfile

from app.main import app
from app.services.history_storage import ReviewRecord, HistoryStorage
from app.services.file_registry import FileRecord

from fastapi.testclient import TestClient

client = TestClient(app)


class TestUploadAPI:
    """上传 API 测试"""

    def test_root_endpoint(self):
        """测试根路径"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data

    def test_health_check(self):
        """测试健康检查"""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_upload_dwg_invalid_type(self):
        """测试上传无效文件类型"""
        # 创建一个假的文件
        files = {"file": ("test.txt", b"test content", "text/plain")}
        response = client.post("/api/v1/upload/dwg", files=files)
        assert response.status_code == 400

    def test_upload_dwg_rejects_dwg_file(self):
        """测试当前版本会直接拒绝 DWG 文件上传"""
        files = {"file": ("drawing.dwg", b"fake dwg", "application/octet-stream")}
        response = client.post("/api/v1/upload/dwg", files=files)
        assert response.status_code == 400
        assert "暂不支持 DWG 上传" in response.json()["detail"]

    def test_upload_contract_invalid_type(self):
        """测试上传无效合同文件类型"""
        files = {"file": ("test.txt", b"test content", "text/plain")}
        response = client.post("/api/v1/upload/contract", files=files)
        assert response.status_code == 400

    def test_list_uploaded_files(self):
        """测试文件列表接口"""
        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = str(Path(tmpdir) / "index.json")
            Path(tmpdir, "drawing.dxf").write_text("dxf")
            Path(tmpdir, "contract.pdf").write_text("pdf")

            registry_records = [
                FileRecord(
                    file_id="dwg-1",
                    filename="drawing.dxf",
                    file_type="dwg",
                    file_path=str(Path(tmpdir) / "drawing.dxf"),
                    suffix=".dxf",
                    uploaded_at="2026-03-18T11:00:00",
                ),
                FileRecord(
                    file_id="contract-1",
                    filename="contract.pdf",
                    file_type="contract",
                    file_path=str(Path(tmpdir) / "contract.pdf"),
                    suffix=".pdf",
                    uploaded_at="2026-03-18T10:00:00",
                ),
            ]

            with patch('app.api.v1.upload.get_file_registry') as mock_registry:
                mock_registry.return_value.list.return_value = registry_records
                response = client.get("/api/v1/upload/list")

            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 2
            assert data["files"][0]["file_id"] == "dwg-1"
            assert data["files"][1]["file_id"] == "contract-1"


class TestReviewAPI:
    """审核 API 测试"""

    def test_create_review_file_not_found(self):
        """测试审核不存在的文件"""
        request = {
            "dwg_file_id": "nonexistent-id"
        }
        response = client.post("/api/v1/review", json=request)
        assert response.status_code == 404

    def test_get_review_not_found(self):
        """测试获取不存在的审核结果"""
        response = client.get("/api/v1/review/nonexistent-id")
        assert response.status_code == 404

    def test_analyze_contract_not_found(self):
        """测试分析不存在的合同"""
        response = client.post("/api/v1/review/contract/nonexistent-id")
        assert response.status_code == 404

    def test_create_review_passes_rule_codes_and_returns_dwg_analysis(self):
        """测试审核接口透传 rule_codes 并始终返回图纸分析"""
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
            review_result = {
                "dwg_review": {
                    "overall_score": 92,
                    "assessment": "通过",
                    "issues": [],
                    "summary": {"total_issues": 0, "by_severity": {}, "by_source": {}, "by_category": {}},
                    "llm_enabled": False,
                },
                "contract_analysis": None,
                "dwg_analysis": {
                    "file_info": {"dxf_version": "AC1032", "units_name": "米", "filename": "drawing.dxf"},
                    "layers": [],
                    "blocks": [],
                    "statistics": {"layer_count": 0, "block_count": 0, "entity_count": 0, "text_count": 0, "dimension_count": 0, "insert_count": 0},
                    "door_window_summary": {"total_doors": 0, "total_windows": 0, "doors": [], "windows": []},
                },
                "contract_dwg_comparison": None,
            }

            with patch('app.api.v1.review.get_uploaded_file') as mock_get_file, \
                 patch('app.api.v1.review.FullReviewService') as mock_service_cls, \
                 patch('app.api.v1.review.get_history_storage') as mock_history:
                mock_get_file.return_value = dwg_record
                mock_service = mock_service_cls.return_value
                mock_service.full_review = AsyncMock(return_value=review_result)
                mock_history.return_value.save.return_value = True

                response = client.post("/api/v1/review", json={
                    "dwg_file_id": "dwg-1",
                    "rule_codes": ["TEXT_001"],
                })

            assert response.status_code == 200
            data = response.json()
            assert data["dwg_analysis"]["file_info"]["filename"] == "drawing.dxf"
            mock_service.full_review.assert_awaited_once()
            assert mock_service.full_review.await_args.kwargs["rule_codes"] == ["TEXT_001"]


class TestHistoryAPI:
    """历史记录 API 测试"""

    def test_get_history_list_empty(self):
        """测试获取空历史记录列表"""
        with patch('app.api.v1.review.get_history_storage') as mock_storage:
            mock_storage.return_value.list.return_value = ([], 0)
            response = client.get("/api/v1/review/history/list")
            assert response.status_code == 200
            data = response.json()
            assert data["records"] == []
            assert data["total"] == 0

    def test_get_history_list_with_records(self):
        """测试获取有记录的历史列表"""
        mock_record = ReviewRecord(
            record_id="test-1",
            file_id="file-1",
            file_name="test.dwg",
            file_type="dwg",
            created_at="2024-01-01T12:00:00",
            overall_score=85,
            assessment="通过",
            issue_count=1
        )

        with patch('app.api.v1.review.get_history_storage') as mock_storage:
            mock_storage.return_value.list.return_value = ([mock_record], 1)
            response = client.get("/api/v1/review/history/list")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert len(data["records"]) == 1
            assert data["records"][0]["record_id"] == "test-1"

    def test_get_history_list_with_filter(self):
        """测试带筛选的历史列表"""
        with patch('app.api.v1.review.get_history_storage') as mock_storage:
            mock_storage.return_value.list.return_value = ([], 0)
            response = client.get(
                "/api/v1/review/history/list",
                params={"assessment": "通过", "file_type": "dwg"}
            )
            assert response.status_code == 200
            mock_storage.return_value.list.assert_called_once()

    def test_get_history_detail_not_found(self):
        """测试获取不存在的历史详情"""
        with patch('app.api.v1.review.get_history_storage') as mock_storage:
            mock_storage.return_value.get_result.return_value = None
            response = client.get("/api/v1/review/history/nonexistent")
            assert response.status_code == 404

    def test_delete_history_not_found(self):
        """测试删除不存在的历史记录"""
        with patch('app.api.v1.review.get_history_storage') as mock_storage:
            mock_storage.return_value.delete.return_value = False
            response = client.delete("/api/v1/review/history/nonexistent")
            assert response.status_code == 404

    def test_delete_history_success(self):
        """测试成功删除历史记录"""
        with patch('app.api.v1.review.get_history_storage') as mock_storage:
            mock_storage.return_value.delete.return_value = True
            response = client.delete("/api/v1/review/history/test-id")
            assert response.status_code == 200
            assert response.json()["success"] is True

    def test_get_statistics(self):
        """测试获取统计信息"""
        mock_stats = {
            "total_reviews": 10,
            "avg_score": 85.5,
            "by_assessment": {"通过": 8, "需修改": 2},
            "by_file_type": {"dwg": 10}
        }

        with patch('app.api.v1.review.get_history_storage') as mock_storage:
            mock_storage.return_value.get_statistics.return_value = mock_stats
            response = client.get("/api/v1/review/statistics")
            assert response.status_code == 200
            data = response.json()
            assert data["total_reviews"] == 10
            assert data["avg_score"] == 85.5


class TestReportDownload:
    """报告下载测试"""

    def test_download_json_not_found(self):
        """测试下载不存在的 JSON 报告"""
        with patch('app.api.v1.review.get_history_storage') as mock_storage:
            mock_storage.return_value.get.return_value = None
            response = client.get("/api/v1/review/report/test-id/json")
            assert response.status_code == 404

    def test_download_pdf_not_found(self):
        """测试下载不存在的 PDF 报告"""
        with patch('app.api.v1.review.get_history_storage') as mock_storage:
            mock_storage.return_value.get.return_value = None
            response = client.get("/api/v1/review/report/test-id/pdf")
            assert response.status_code == 404

    def test_download_json_success(self):
        """测试成功下载 JSON 报告"""
        mock_record = ReviewRecord(
            record_id="test-json",
            file_id="file-1",
            file_name="test.dwg",
            file_type="dwg",
            created_at="2024-01-01T12:00:00",
            overall_score=85,
            assessment="通过",
            issue_count=1
        )

        mock_result = {
            "dwg_review": {
                "overall_score": 85,
                "assessment": "通过",
                "issues": [],
                "summary": {},
                "llm_enabled": False
            }
        }

        with patch('app.api.v1.review.get_history_storage') as mock_storage:
            mock_storage.return_value.get.return_value = mock_record
            mock_storage.return_value.get_result.return_value = mock_result
            response = client.get("/api/v1/review/report/test-json/json")
            assert response.status_code == 200
            assert response.headers["content-type"] == "application/json"

    def test_download_pdf_success(self):
        """测试成功下载 PDF 报告"""
        mock_record = ReviewRecord(
            record_id="test-pdf",
            file_id="file-1",
            file_name="test.dwg",
            file_type="dwg",
            created_at="2024-01-01T12:00:00",
            overall_score=85,
            assessment="通过",
            issue_count=0
        )

        mock_result = {
            "dwg_review": {
                "overall_score": 85,
                "assessment": "通过",
                "issues": [],
                "summary": {},
                "llm_enabled": False
            }
        }

        with patch('app.api.v1.review.get_history_storage') as mock_storage:
            mock_storage.return_value.get.return_value = mock_record
            mock_storage.return_value.get_result.return_value = mock_result
            response = client.get("/api/v1/review/report/test-pdf/pdf")
            assert response.status_code == 200
