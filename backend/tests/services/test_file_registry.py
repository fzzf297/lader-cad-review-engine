"""
文件注册表服务测试
"""
from pathlib import Path

from app.services.file_registry import FileRecord, get_file_registry


class TestFileRegistry:
    """文件注册表测试"""

    def test_register_and_get_record(self, tmp_path):
        registry = get_file_registry(str(tmp_path / "index.json"))

        record = FileRecord(
            file_id="dwg-1",
            filename="test.dwg",
            file_type="dwg",
            file_path="/tmp/test.dxf",
            suffix=".dxf",
            converted=True,
            uploaded_at="2026-03-18T10:00:00",
        )

        registry.register(record)
        loaded = registry.get("dwg-1")

        assert loaded is not None
        assert loaded.filename == "test.dwg"
        assert loaded.converted is True

    def test_list_sorted_and_filtered(self, tmp_path):
        registry = get_file_registry(str(tmp_path / "index.json"))
        registry.register(FileRecord(
            file_id="contract-1",
            filename="contract.pdf",
            file_type="contract",
            file_path="/tmp/contract.pdf",
            suffix=".pdf",
            uploaded_at="2026-03-18T09:00:00",
        ))
        registry.register(FileRecord(
            file_id="dwg-1",
            filename="drawing.dxf",
            file_type="dwg",
            file_path="/tmp/drawing.dxf",
            suffix=".dxf",
            uploaded_at="2026-03-18T11:00:00",
        ))

        records = registry.list()
        assert [record.file_id for record in records] == ["dwg-1", "contract-1"]

        dwg_records = registry.list(file_type="dwg")
        assert len(dwg_records) == 1
        assert dwg_records[0].file_id == "dwg-1"

    def test_load_from_disk(self, tmp_path):
        storage_path = tmp_path / "index.json"
        registry = get_file_registry(str(storage_path))
        registry.register(FileRecord(
            file_id="dwg-1",
            filename="persisted.dxf",
            file_type="dwg",
            file_path="/tmp/persisted.dxf",
            suffix=".dxf",
            uploaded_at="2026-03-18T12:00:00",
        ))

        reloaded = get_file_registry(str(storage_path))
        assert reloaded.get("dwg-1") is not None
