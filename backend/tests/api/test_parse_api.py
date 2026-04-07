"""
解析 API 测试
"""
from pathlib import Path
from unittest.mock import AsyncMock, patch
import tempfile

from fastapi.testclient import TestClient

from app.main import app
from app.services.file_registry import FileRecord

client = TestClient(app)


class TestParseAPI:
    def test_legend_count_returns_structured_result(self):
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
            payload = {
                "query": "编码感烟火灾探测器",
                "matched_label_texts": ["图例 编码感烟火灾探测器"],
                "target_signature": {"block_name": "SMOKE_SENSOR", "source": "label_nearby_insert"},
                "total_matches": 3,
                "excluded_as_legend": 1,
                "actual_count": 2,
                "matches": [
                    {"x": 100, "y": 100, "z": 0, "layer": "消防", "block_name": "SMOKE_SENSOR", "handle": "A1", "reason": "主图实例"},
                ],
                "excluded_matches": [
                    {"x": -4900, "y": 4900, "z": 0, "layer": "说明", "block_name": "SMOKE_SENSOR", "handle": "L1", "reason": "位于图例候选区域"},
                ],
                "explanation": "统计完成",
                "confidence": 0.91,
            }

            with patch("app.api.v1.parse.get_uploaded_file", return_value=dwg_record), \
                 patch("app.api.v1.parse.ParseService") as mock_parse_service_cls:
                mock_service = mock_parse_service_cls.return_value
                mock_service.count_legend = AsyncMock(return_value=payload)

                response = client.post("/api/v1/parse/legend-count", json={
                    "file_id": "dwg-1",
                    "query": "编码感烟火灾探测器",
                    "use_llm": False,
                })

            assert response.status_code == 200
            data = response.json()
            assert data["actual_count"] == 2
            assert data["excluded_as_legend"] == 1
            assert data["target_signature"]["block_name"] == "SMOKE_SENSOR"

    def test_legend_items_returns_discovered_list(self):
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
            payload = {
                "file_id": "dwg-1",
                "total_items": 1,
                "items": [
                    {
                        "label_text": "图例 编码感烟火灾探测器",
                        "normalized_name": "编码感烟火灾探测器",
                        "block_name": "SMOKE_SENSOR",
                        "total_matches": 3,
                        "estimated_actual_count": 2,
                        "excluded_as_legend": 1,
                        "confidence": 0.81,
                        "source": "label_nearby_insert",
                    }
                ],
            }

            with patch("app.api.v1.parse.get_uploaded_file", return_value=dwg_record), \
                 patch("app.api.v1.parse.ParseService") as mock_parse_service_cls:
                mock_service = mock_parse_service_cls.return_value
                mock_service.discover_legends = AsyncMock(return_value=payload)

                response = client.get("/api/v1/parse/legend-items/dwg-1")

            assert response.status_code == 200
            data = response.json()
            assert data["total_items"] == 1
            assert data["items"][0]["normalized_name"] == "编码感烟火灾探测器"

    def test_dwg_preview_returns_entities(self):
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
            payload = {
                "file_id": "dwg-1",
                "bounds": {"min_x": 0, "max_x": 100, "min_y": 0, "max_y": 100},
                "entities": [
                    {"type": "LINE", "start": {"x": 0, "y": 0}, "end": {"x": 100, "y": 0}},
                    {"type": "CIRCLE", "center": {"x": 50, "y": 50}, "radius": 10},
                    {"type": "ARC", "center": {"x": 50, "y": 50}, "radius": 20, "start_angle": 0, "end_angle": 90},
                    {"type": "TEXT", "insert": {"x": 20, "y": 30}, "content": "一层平面图", "height": 3.5, "rotation": 0},
                ],
            }

            with patch("app.api.v1.parse.get_uploaded_file", return_value=dwg_record), \
                 patch("app.api.v1.parse.ParseService") as mock_parse_service_cls:
                mock_service = mock_parse_service_cls.return_value
                mock_service.get_dwg_preview = AsyncMock(return_value=payload)

                response = client.get("/api/v1/parse/dwg/dwg-1/preview")

            assert response.status_code == 200
            data = response.json()
            assert data["bounds"]["max_x"] == 100
            assert data["entities"][0]["type"] == "LINE"
            assert data["entities"][2]["type"] == "ARC"
            assert data["entities"][3]["content"] == "一层平面图"

    def test_experimental_vision_regions_returns_region_groups(self):
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
            payload = {
                "file_id": "dwg-1",
                "enabled": True,
                "provider": "heuristic-preview",
                "model": "preview-v1",
                "overview_image": "data:image/svg+xml;base64,ZmFrZQ==",
                "legend_regions": [
                    {
                        "region_id": "legend-1",
                        "label": "固定挡烟垂壁",
                        "min_x": 0,
                        "max_x": 100,
                        "min_y": 0,
                        "max_y": 100,
                        "confidence": 0.86,
                        "reason": "候选图例区",
                        "image_data": "data:image/svg+xml;base64,ZmFrZQ==",
                    }
                ],
                "content_regions": [],
                "excluded_regions": [],
            }

            with patch("app.api.v1.parse.get_uploaded_file", return_value=dwg_record), \
                 patch("app.api.v1.parse.ParseService") as mock_parse_service_cls:
                mock_service = mock_parse_service_cls.return_value
                mock_service.experimental_vision_regions = AsyncMock(return_value=payload)

                response = client.post("/api/v1/parse/experimental/vision/regions", json={
                    "file_id": "dwg-1",
                })

            assert response.status_code == 200
            data = response.json()
            assert data["provider"] == "heuristic-preview"
            assert data["legend_regions"][0]["label"] == "固定挡烟垂壁"

    def test_experimental_vision_classify_returns_three_groups(self):
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
            payload = {
                "file_id": "dwg-1",
                "legend_name": "固定挡烟垂壁",
                "enabled": True,
                "provider": "heuristic-preview",
                "model": "preview-v1",
                "strategy": "vision_assisted_block",
                "overview_image": "data:image/svg+xml;base64,ZmFrZQ==",
                "legend_regions": [],
                "confirmed_matches": [
                    {
                        "x": 120.0,
                        "y": 240.0,
                        "z": 0.0,
                        "layer": "消防",
                        "block_name": "SMOKE_WALL",
                        "handle": "C1",
                        "reason": "确认计入",
                        "confidence": 0.81,
                        "image_data": "data:image/svg+xml;base64,ZmFrZQ==",
                    }
                ],
                "uncertain_matches": [
                    {
                        "x": 150.0,
                        "y": 260.0,
                        "z": 0.0,
                        "layer": "消防",
                        "block_name": "SMOKE_WALL",
                        "handle": "U1",
                        "reason": "需要人工复核",
                        "confidence": 0.47,
                        "image_data": "data:image/svg+xml;base64,ZmFrZQ==",
                    }
                ],
                "excluded_matches": [
                    {
                        "x": 20.0,
                        "y": 40.0,
                        "z": 0.0,
                        "layer": "说明",
                        "block_name": "SMOKE_WALL",
                        "handle": "E1",
                        "reason": "图例样例区",
                        "confidence": 0.93,
                        "image_data": "data:image/svg+xml;base64,ZmFrZQ==",
                    }
                ],
                "summary": {
                    "confirmed_count": 1,
                    "uncertain_count": 1,
                    "excluded_count": 1,
                },
                "explanation": "实验识别说明",
            }

            with patch("app.api.v1.parse.get_uploaded_file", return_value=dwg_record), \
                 patch("app.api.v1.parse.ParseService") as mock_parse_service_cls:
                mock_service = mock_parse_service_cls.return_value
                mock_service.experimental_vision_classify = AsyncMock(return_value=payload)

                response = client.post("/api/v1/parse/experimental/vision/classify", json={
                    "file_id": "dwg-1",
                    "legend_name": "固定挡烟垂壁",
                })

            assert response.status_code == 200
            data = response.json()
            assert data["strategy"] == "vision_assisted_block"
            assert data["summary"]["confirmed_count"] == 1
            assert data["uncertain_matches"][0]["handle"] == "U1"
            assert data["excluded_matches"][0]["reason"] == "图例样例区"
