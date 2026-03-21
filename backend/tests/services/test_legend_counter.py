"""
图例计数服务测试
"""
from unittest.mock import AsyncMock, Mock, patch

from app.parsers.dxf_parser import DxfParseResult
from app.services.legend_counter import LegendCounter
from app.services.legend_template_service import get_legend_template_service


def build_sample_result() -> DxfParseResult:
    blocks = {
        "SMOKE_SENSOR": {
            "name": "SMOKE_SENSOR",
            "entities": [{"type": "CIRCLE"}, {"type": "LINE"}],
            "entity_count": 2,
            "insert_count": 4,
            "is_door_window": False,
        },
        "SMOKE_SENSOR_ALT": {
            "name": "SMOKE_SENSOR_ALT",
            "entities": [{"type": "CIRCLE"}, {"type": "LINE"}],
            "entity_count": 2,
            "insert_count": 1,
            "is_door_window": False,
        },
    }
    result = DxfParseResult(
        file_info={"filename": "sample.dxf"},
        blocks=blocks,
        texts=[
            {"type": "TEXT", "content": "图例 编码感烟火灾探测器", "insert": {"x": -5000, "y": 5000, "z": 0}, "layer": "说明"},
            {"type": "TEXT", "content": "设备名称", "insert": {"x": -4700, "y": 5000, "z": 0}, "layer": "说明"},
            {"type": "TEXT", "content": "房间A", "insert": {"x": 100, "y": 100, "z": 0}, "layer": "标注"},
        ],
        inserts=[
            {"type": "INSERT", "name": "SMOKE_SENSOR", "insert": {"x": -4900, "y": 4900, "z": 0}, "layer": "说明", "handle": "L1", "attribs": {}},
            {"type": "INSERT", "name": "SMOKE_SENSOR", "insert": {"x": 100, "y": 100, "z": 0}, "layer": "消防", "handle": "A1", "attribs": {}},
            {"type": "INSERT", "name": "SMOKE_SENSOR", "insert": {"x": 200, "y": 200, "z": 0}, "layer": "消防", "handle": "A2", "attribs": {}},
            {"type": "INSERT", "name": "SMOKE_SENSOR_ALT", "insert": {"x": 300, "y": 300, "z": 0}, "layer": "消防", "handle": "A3", "attribs": {}},
        ],
        entities=[
            {"type": "INSERT", "insert": {"x": 100, "y": 100, "z": 0}},
            {"type": "INSERT", "insert": {"x": 200, "y": 200, "z": 0}},
            {"type": "INSERT", "insert": {"x": 300, "y": 300, "z": 0}},
            {"type": "LINE", "start": {"x": 0, "y": 0, "z": 0}},
            {"type": "LINE", "start": {"x": 500, "y": 500, "z": 0}},
        ],
        block_signatures={
            "SMOKE_SENSOR": {
                "entity_types": ["CIRCLE", "LINE"],
                "entity_type_counts": {"CIRCLE": 1, "LINE": 1},
                "entity_count": 2,
            },
            "SMOKE_SENSOR_ALT": {
                "entity_types": ["CIRCLE", "LINE"],
                "entity_type_counts": {"CIRCLE": 1, "LINE": 1},
                "entity_count": 2,
            },
        },
        raw_texts=[],
    )
    return result


class TestLegendCounter:
    async def test_count_excludes_legend_instances(self, tmp_path):
        service = get_legend_template_service(str(tmp_path / "legend_templates.json"))
        counter = LegendCounter()
        counter.template_service = service

        result = await counter.count(
            dxf_result=build_sample_result(),
            query="编码感烟火灾探测器",
        )

        assert result.total_matches == 3
        assert result.excluded_as_legend == 1
        assert result.actual_count == 2
        assert any("图例候选区域" in item["reason"] for item in result.excluded_matches)

    async def test_count_can_save_and_reuse_template(self, tmp_path):
        service = get_legend_template_service(str(tmp_path / "legend_templates.json"))
        counter = LegendCounter()
        counter.template_service = service
        dxf_result = build_sample_result()

        first = await counter.count(
            dxf_result=dxf_result,
            query="编码感烟火灾探测器",
            save_template=True,
            template_name="烟感",
        )
        second = await counter.count(
            dxf_result=dxf_result,
            query="统计烟感数量",
        )

        assert first.actual_count == 2
        assert second.actual_count == 2
        assert second.target_signature["source"] == "template"

    async def test_count_returns_low_confidence_when_target_missing(self, tmp_path):
        service = get_legend_template_service(str(tmp_path / "legend_templates.json"))
        counter = LegendCounter()
        counter.template_service = service

        result = await counter.count(
            dxf_result=build_sample_result(),
            query="不存在的设备",
        )

        assert result.actual_count == 0
        assert result.confidence < 0.2

    async def test_count_uses_llm_keyword_expansion_when_enabled(self, tmp_path):
        service = get_legend_template_service(str(tmp_path / "legend_templates.json"))
        counter = LegendCounter()
        counter.template_service = service
        mock_expander = Mock()
        mock_expander.expand = AsyncMock(return_value=["编码感烟火灾探测器"])

        with patch("app.services.legend_counter.get_legend_query_expansion_service", return_value=mock_expander):
            sparse_result = build_sample_result()
            sparse_result.texts = [{"type": "TEXT", "content": "图例 编码感烟火灾探测器", "insert": {"x": -5000, "y": 5000, "z": 0}, "layer": "说明"}]
            result = await counter.count(
                dxf_result=sparse_result,
                query="火灾探头",
                use_llm=True,
            )

        mock_expander.expand.assert_awaited_once_with("火灾探头")
        assert result.actual_count == 2

    async def test_count_with_llm_flag_gracefully_falls_back_without_service(self, tmp_path):
        service = get_legend_template_service(str(tmp_path / "legend_templates.json"))
        counter = LegendCounter()
        counter.template_service = service

        with patch("app.services.legend_counter.get_legend_query_expansion_service", return_value=None):
            result = await counter.count(
                dxf_result=build_sample_result(),
                query="编码感烟火灾探测器",
                use_llm=True,
            )

        assert result.actual_count == 2

    async def test_count_prefers_explicit_legend_zone_over_far_cluster(self, tmp_path):
        service = get_legend_template_service(str(tmp_path / "legend_templates.json"))
        counter = LegendCounter()
        counter.template_service = service

        result = DxfParseResult(
            file_info={"filename": "sample.dxf"},
            blocks={
                "ALARM": {
                    "name": "ALARM",
                    "entities": [{"type": "CIRCLE"}],
                    "entity_count": 1,
                    "insert_count": 3,
                    "is_door_window": False,
                }
            },
            texts=[
                {"type": "TEXT", "content": "强电主要设备图例表", "insert": {"x": -310000, "y": -70000, "z": 0}, "layer": "说明"},
                {"type": "TEXT", "content": "火灾声光报警器", "insert": {"x": -306857.396, "y": -75444.929, "z": 0}, "layer": "电-文字"},
            ],
            inserts=[
                {"type": "INSERT", "name": "ALARM", "insert": {"x": -307807.396, "y": -76144.84, "z": 0}, "layer": "说明", "handle": "L1", "attribs": {}},
                {"type": "INSERT", "name": "ALARM", "insert": {"x": 12000, "y": -206440.864, "z": 0}, "layer": "消防", "handle": "A1", "attribs": {}},
                {"type": "INSERT", "name": "ALARM", "insert": {"x": -26635.178, "y": -273832.256, "z": 0}, "layer": "消防", "handle": "A2", "attribs": {}},
            ],
            entities=[
                {"type": "INSERT", "insert": {"x": -307807.396, "y": -76144.84, "z": 0}},
                {"type": "INSERT", "insert": {"x": 12000, "y": -206440.864, "z": 0}},
                {"type": "INSERT", "insert": {"x": -26635.178, "y": -273832.256, "z": 0}},
                {"type": "LINE", "start": {"x": 0, "y": 0, "z": 0}},
                {"type": "LINE", "start": {"x": 1000, "y": 1000, "z": 0}},
            ],
            block_signatures={
                "ALARM": {
                    "entity_types": ["CIRCLE"],
                    "entity_type_counts": {"CIRCLE": 1},
                    "entity_count": 1,
                }
            },
        )

        counted = await counter.count(result, "火灾声光报警器")

        assert counted.total_matches == 3
        assert counted.excluded_as_legend == 1
        assert counted.actual_count == 2

    async def test_count_excludes_note_callout_sample_pair(self, tmp_path):
        service = get_legend_template_service(str(tmp_path / "legend_templates.json"))
        counter = LegendCounter()
        counter.template_service = service

        result = DxfParseResult(
            file_info={"filename": "sample.dxf"},
            blocks={
                "SMOKE_SENSOR": {
                    "name": "SMOKE_SENSOR",
                    "entities": [{"type": "CIRCLE"}],
                    "entity_count": 1,
                    "insert_count": 4,
                    "is_door_window": False,
                }
            },
            texts=[
                {"type": "TEXT", "content": "图例 编码感烟火灾探测器", "insert": {"x": -306857.0, "y": -72645.0, "z": 0}, "layer": "说明"},
                {"type": "TEXT", "content": "至图书馆消防总控制室", "insert": {"x": -25000.0, "y": 14500.0, "z": 0}, "layer": "标注"},
                {"type": "TEXT", "content": "WDZN-KYJY-2x2.5-JDG20-FC", "insert": {"x": -25500.0, "y": 13500.0, "z": 0}, "layer": "标注"},
            ],
            inserts=[
                {"type": "INSERT", "name": "SMOKE_SENSOR", "insert": {"x": -307807.0, "y": -72495.0, "z": 0}, "layer": "说明", "handle": "L1", "attribs": {}},
                {"type": "INSERT", "name": "SMOKE_SENSOR", "insert": {"x": -27289.2, "y": 13967.9, "z": 0}, "layer": "消防", "handle": "S1", "attribs": {}},
                {"type": "INSERT", "name": "SMOKE_SENSOR", "insert": {"x": -22459.6, "y": 13967.9, "z": 0}, "layer": "消防", "handle": "S2", "attribs": {}},
                {"type": "INSERT", "name": "SMOKE_SENSOR", "insert": {"x": 100.0, "y": 100.0, "z": 0}, "layer": "消防", "handle": "A1", "attribs": {}},
            ],
            entities=[
                {"type": "INSERT", "insert": {"x": -307807.0, "y": -72495.0, "z": 0}},
                {"type": "INSERT", "insert": {"x": -27289.2, "y": 13967.9, "z": 0}},
                {"type": "INSERT", "insert": {"x": -22459.6, "y": 13967.9, "z": 0}},
                {"type": "INSERT", "insert": {"x": 100.0, "y": 100.0, "z": 0}},
                {"type": "LINE", "start": {"x": 0, "y": 0, "z": 0}},
            ],
            block_signatures={
                "SMOKE_SENSOR": {
                    "entity_types": ["CIRCLE"],
                    "entity_type_counts": {"CIRCLE": 1},
                    "entity_count": 1,
                }
            },
            raw_texts=[],
        )

        counted = await counter.count(result, "编码感烟火灾探测器")

        assert counted.total_matches == 4
        assert counted.excluded_as_legend == 3
        assert counted.actual_count == 1
        assert sum("位于注释引线样例区" in item["reason"] for item in counted.excluded_matches) == 2

    async def test_llm_review_can_restore_soft_excluded_candidate(self, tmp_path):
        service = get_legend_template_service(str(tmp_path / "legend_templates.json"))
        counter = LegendCounter()
        counter.template_service = service

        result = DxfParseResult(
            file_info={"filename": "sample.dxf"},
            blocks={
                "SMOKE_SENSOR": {
                    "name": "SMOKE_SENSOR",
                    "entities": [{"type": "CIRCLE"}],
                    "entity_count": 1,
                    "insert_count": 3,
                    "is_door_window": False,
                }
            },
            texts=[
                {"type": "TEXT", "content": "图例 编码感烟火灾探测器", "insert": {"x": -306857.0, "y": -72645.0, "z": 0}, "layer": "说明"},
                {"type": "TEXT", "content": "至图书馆消防总控制室", "insert": {"x": -25000.0, "y": 14500.0, "z": 0}, "layer": "标注"},
            ],
            inserts=[
                {"type": "INSERT", "name": "SMOKE_SENSOR", "insert": {"x": -307807.0, "y": -72495.0, "z": 0}, "layer": "说明", "handle": "L1", "attribs": {}},
                {"type": "INSERT", "name": "SMOKE_SENSOR", "insert": {"x": -27289.2, "y": 13967.9, "z": 0}, "layer": "消防", "handle": "S1", "attribs": {}},
                {"type": "INSERT", "name": "SMOKE_SENSOR", "insert": {"x": -22459.6, "y": 13967.9, "z": 0}, "layer": "消防", "handle": "S2", "attribs": {}},
            ],
            entities=[
                {"type": "INSERT", "insert": {"x": -307807.0, "y": -72495.0, "z": 0}},
                {"type": "INSERT", "insert": {"x": -27289.2, "y": 13967.9, "z": 0}},
                {"type": "INSERT", "insert": {"x": -22459.6, "y": 13967.9, "z": 0}},
                {"type": "LINE", "start": {"x": 0, "y": 0, "z": 0}},
                {"type": "LINE", "start": {"x": 1000, "y": 1000, "z": 0}},
            ],
            block_signatures={
                "SMOKE_SENSOR": {
                    "entity_types": ["CIRCLE"],
                    "entity_type_counts": {"CIRCLE": 1},
                    "entity_count": 1,
                }
            },
            raw_texts=[],
        )

        mock_reviewer = Mock()
        mock_reviewer.review = AsyncMock(return_value={
            "decision": "keep",
            "confidence": 0.91,
            "reason": "只有一个边界点，优先保留",
        })
        counter.point_review_service = mock_reviewer
        counter._classify_candidate = Mock(side_effect=[
            ["位于图例候选区域"],
            ["位于注释引线样例区"],
            [],
        ])

        counted = await counter.count(result, "编码感烟火灾探测器", use_llm=True)

        assert counted.actual_count == 2
        assert counted.excluded_as_legend == 1
        assert any(item["handle"] == "S1" for item in counted.matches)
        mock_reviewer.review.assert_awaited_once()

    async def test_discover_returns_candidate_legend_items(self, tmp_path):
        service = get_legend_template_service(str(tmp_path / "legend_templates.json"))
        counter = LegendCounter()
        counter.template_service = service

        items = await counter.discover(build_sample_result())

        assert len(items) >= 1
        assert items[0]["normalized_name"] == "编码感烟火灾探测器"
        assert items[0]["block_name"] == "SMOKE_SENSOR"
        assert items[0]["estimated_actual_count"] == 2
