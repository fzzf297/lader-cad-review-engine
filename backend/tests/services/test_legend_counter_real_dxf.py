from pathlib import Path

import pytest

from app.parsers.dxf_parser import DxfParser
from app.services.legend_counter import LegendCounter


REAL_DXF_PATH = Path("/Users/fzzf/Downloads/ImageToStl.com_20250819西农大3#教学楼电气_t3(1).dxf")


@pytest.mark.skipif(not REAL_DXF_PATH.exists(), reason="real DXF fixture not available")
class TestLegendCounterRealDxf:
    @pytest.mark.asyncio
    async def test_real_dxf_counts_smoke_detector(self):
        parser = DxfParser()
        counter = LegendCounter()

        result = parser.parse(str(REAL_DXF_PATH))
        counted = await counter.count(result, "编码感烟火灾探测器")

        assert counted.total_matches == 191
        assert counted.excluded_as_legend == 7
        assert counted.actual_count == 184

    @pytest.mark.asyncio
    async def test_real_dxf_counts_sound_light_alarm(self):
        parser = DxfParser()
        counter = LegendCounter()

        result = parser.parse(str(REAL_DXF_PATH))
        counted = await counter.count(result, "火灾声光报警器")

        assert counted.total_matches == 16
        assert counted.excluded_as_legend == 5
        assert counted.actual_count == 11
