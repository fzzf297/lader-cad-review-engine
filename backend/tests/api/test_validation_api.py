"""
验证 API 测试
"""
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.file_registry import FileRecord

client = TestClient(app)


class TestValidationAPI:
    """合同-图纸验证接口测试"""

    def test_validate_contract_dwg_uses_registry_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            contract_path = Path(tmpdir) / "contract.pdf"
            dwg_path = Path(tmpdir) / "drawing.dxf"
            contract_path.write_text("contract")
            dwg_path.write_text("dxf")

            contract_record = FileRecord(
                file_id="contract-1",
                filename="contract.pdf",
                file_type="contract",
                file_path=str(contract_path),
                suffix=".pdf",
            )
            dwg_record = FileRecord(
                file_id="dwg-1",
                filename="drawing.dxf",
                file_type="dwg",
                file_path=str(dwg_path),
                suffix=".dxf",
            )

            with patch('app.api.v1.validate.get_uploaded_file') as mock_get_file, \
                 patch('app.api.v1.validate.ParseService') as mock_parse_service_cls, \
                 patch('app.api.v1.validate.ContractDwgValidator') as mock_validator_cls:
                mock_get_file.side_effect = [contract_record, dwg_record]
                mock_parse_service = mock_parse_service_cls.return_value
                mock_parse_service.parse_contract.return_value = object()
                mock_parse_service.analyze_contract = AsyncMock(return_value=object())
                mock_parse_service.parse_dxf = AsyncMock(return_value=object())

                report = SimpleNamespace()
                mock_validator_cls.return_value.validate = AsyncMock(return_value=report)
                report.overall_match = 95
                report.status = "完全匹配"
                report.summary = {
                    "total_contract_items": 1,
                    "matched": 1,
                    "partial": 0,
                    "missing": 0,
                    "extra": 0,
                    "total_doors": 1,
                    "total_windows": 0,
                }
                report.matches = []
                report.mismatches = []
                report.extra_in_dwg = []
                report.suggestions = []

                response = client.post("/api/v1/validate/contract-dwg?contract_file_id=contract-1&dwg_file_id=dwg-1")

            assert response.status_code == 200
            data = response.json()
            assert data["contract_filename"] == "contract.pdf"
            assert data["dwg_filename"] == "drawing.dxf"
