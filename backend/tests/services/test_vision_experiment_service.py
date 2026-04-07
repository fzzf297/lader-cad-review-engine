from unittest.mock import AsyncMock, Mock

from app.parsers.dxf_parser import DxfParseResult
from app.services.vision_experiment_service import VisionExperimentService


def build_vision_result() -> DxfParseResult:
    return DxfParseResult(
        file_info={"filename": "vision-sample.dxf"},
        texts=[
            {"type": "TEXT", "content": "图例", "insert": {"x": 0, "y": 0, "z": 0}, "layer": "说明"},
            {"type": "TEXT", "content": "编码感烟火灾探测器", "insert": {"x": 200, "y": 0, "z": 0}, "layer": "说明"},
            {"type": "TEXT", "content": "教室", "insert": {"x": 12000, "y": 5000, "z": 0}, "layer": "标注"},
        ],
        inserts=[
            {"type": "INSERT", "name": "$DorLib2D$00000001", "insert": {"x": 260, "y": 0, "z": 0}, "layer": "0", "handle": "L1", "attribs": {}},
            {"type": "INSERT", "name": "$DorLib2D$00000001", "insert": {"x": 12000, "y": 5000, "z": 0}, "layer": "消防", "handle": "A1", "attribs": {}},
        ],
        entities=[
            {"type": "LINE", "start": {"x": 0, "y": 0}, "end": {"x": 13000, "y": 5000}},
            {"type": "TEXT", "insert": {"x": 200, "y": 0}, "content": "编码感烟火灾探测器"},
            {"type": "TEXT", "insert": {"x": 12000, "y": 5000}, "content": "教室"},
        ],
        blocks={
            "$DorLib2D$00000001": {
                "name": "$DorLib2D$00000001",
                "entities": [{"type": "LINE"}],
                "entity_count": 1,
                "insert_count": 2,
                "is_door_window": False,
            }
        },
        block_signatures={
            "$DorLib2D$00000001": {
                "entity_types": ["LINE"],
                "entity_type_counts": {"LINE": 1},
                "entity_count": 1,
            }
        },
        raw_texts=[],
    )


class TestVisionExperimentService:
    async def test_qwen_provider_can_promote_candidate_to_confirmed(self):
        service = VisionExperimentService()
        service.provider = "qwen"
        service.max_model_candidates = 8
        service.vision_reviewer = Mock()
        service.vision_reviewer.model = "qwen3-vl-plus"
        service.vision_reviewer.review_candidate = AsyncMock(
            return_value={
                "classification": "confirmed",
                "confidence": 0.88,
                "reason": "局部图与图例符号一致，位于主图内容区。",
            }
        )

        preview = {
            "file_id": "dwg-1",
            "bounds": {"min_x": -1000, "max_x": 13000, "min_y": -1000, "max_y": 6000},
            "entities": [
                {"type": "LINE", "start": {"x": 0, "y": 0}, "end": {"x": 13000, "y": 5000}},
                {"type": "TEXT", "insert": {"x": 200, "y": 0}, "content": "编码感烟火灾探测器"},
                {"type": "TEXT", "insert": {"x": 12000, "y": 5000}, "content": "教室"},
            ],
        }

        result = await service.classify_legend(
            dxf_result=build_vision_result(),
            preview=preview,
            file_id="dwg-1",
            legend_name="编码感烟火灾探测器",
        )

        assert result["provider"] == "qwen"
        assert result["model"] == "qwen3-vl-plus"
        assert result["summary"]["confirmed_count"] == 1
        assert result["summary"]["excluded_count"] == 1
        assert result["confirmed_matches"][0]["handle"] == "A1"
        assert "局部图与图例符号一致" in result["confirmed_matches"][0]["reason"]
