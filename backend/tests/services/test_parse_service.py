"""
解析服务测试
"""
from unittest.mock import AsyncMock

import pytest

from app.parsers.dxf_parser import DxfParseResult
from app.services.parse_service import ParseService


@pytest.mark.asyncio
async def test_get_dwg_preview_includes_arc_text_and_insert_expansion():
    service = ParseService()
    service.parse_dxf = AsyncMock(return_value=DxfParseResult(
        entities=[
            {
                "type": "LINE",
                "start": {"x": 0.0, "y": 0.0},
                "end": {"x": 100.0, "y": 0.0},
            },
            {
                "type": "ARC",
                "center": {"x": 50.0, "y": 50.0},
                "radius": 25.0,
                "start_angle": 0.0,
                "end_angle": 90.0,
            },
            {
                "type": "TEXT",
                "insert": {"x": 10.0, "y": 20.0},
                "content": "一层火灾自动报警平面图",
                "height": 3.5,
                "rotation": 0.0,
            },
        ],
        inserts=[
            {
                "type": "INSERT",
                "name": "LEGEND_BLOCK",
                "insert": {"x": 200.0, "y": 300.0},
                "scale": {"x": 1.0, "y": 1.0},
                "rotation": 0.0,
            }
        ],
        blocks={
            "LEGEND_BLOCK": {
                "name": "LEGEND_BLOCK",
                "entities": [
                    {
                        "type": "LINE",
                        "start": {"x": 0.0, "y": 0.0},
                        "end": {"x": 20.0, "y": 0.0},
                    },
                    {
                        "type": "TEXT",
                        "insert": {"x": 5.0, "y": 8.0},
                        "content": "声光报警器",
                        "height": 2.5,
                        "rotation": 0.0,
                    },
                ],
            }
        },
    ))

    result = await service.get_dwg_preview("/tmp/fake.dxf", "dwg-1")

    assert result["file_id"] == "dwg-1"
    entity_types = [entity["type"] for entity in result["entities"]]
    assert "LINE" in entity_types
    assert "ARC" in entity_types
    assert "TEXT" in entity_types
    assert any(
        entity["type"] == "TEXT" and entity.get("content") == "声光报警器"
        for entity in result["entities"]
    )
    assert result["bounds"]["max_x"] >= 200.0
    assert result["bounds"]["max_y"] >= 300.0
