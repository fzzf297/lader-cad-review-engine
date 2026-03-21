"""
合同-图纸比对测试
"""
import pytest
from app.services.review_service import (
    ContractDwgMatcher,
    WorkItem,
    ContractAnalysisResult,
)


class TestWorkItem:
    """工作项测试"""

    def test_create_work_item(self):
        """测试创建工作项"""
        item = WorkItem(
            name="铝合金门M1021",
            category="门窗",
            quantity=50,
            unit="套",
            specification="1000x2100"
        )

        assert item.name == "铝合金门M1021"
        assert item.category == "门窗"
        assert item.quantity == 50

    def test_default_values(self):
        """测试默认值"""
        item = WorkItem(
            name="测试项目",
            category="其他",
            quantity=0,
            unit=""
        )

        assert item.specification == ""
        assert item.location == ""


class TestContractDwgMatcher:
    """合同-图纸比对引擎测试"""

    def setup_method(self):
        self.matcher = ContractDwgMatcher()

    def test_categorize_block_door(self):
        """测试分类门图块"""
        assert self.matcher._categorize_block("M1021") == "门窗"
        assert self.matcher._categorize_block("DOOR_ENTRANCE") == "门窗"

    def test_categorize_block_window(self):
        """测试分类窗图块"""
        assert self.matcher._categorize_block("C1515") == "门窗"
        assert self.matcher._categorize_block("WINDOW_01") == "门窗"

    def test_categorize_block_pipe(self):
        """测试分类管道图块"""
        assert self.matcher._categorize_block("PIPE_DN100") == "管道"
        assert self.matcher._categorize_block("DUCT_01") == "管道"

    def test_categorize_block_electrical(self):
        """测试分类电气图块"""
        assert self.matcher._categorize_block("SWITCH_01") == "电气"
        assert self.matcher._categorize_block("ELEC_PANEL") == "电气"

    def test_categorize_block_other(self):
        """测试分类其他图块"""
        assert self.matcher._categorize_block("FURNITURE_01") == "其他"
        assert self.matcher._categorize_block("UNKNOWN") == "其他"

    def test_extract_dwg_statistics(self, sample_dxf_data):
        """测试提取图纸统计"""
        stats = self.matcher._extract_dwg_statistics(sample_dxf_data)

        assert "blocks_by_category" in stats
        assert "total_blocks" in stats
        assert stats["total_blocks"] > 0

    def test_match_single_item_matched(self):
        """测试匹配单个项目 - 匹配"""
        contract_item = WorkItem(
            name="铝合金门",
            category="门窗",
            quantity=5,
            unit="套"
        )

        dwg_stats = {
            "blocks_by_category": {
                "门窗": [
                    {"name": "M1021", "count": 5}
                ]
            }
        }

        result = self.matcher._match_single_item(contract_item, dwg_stats, {})

        assert result.match_status == "matched"
        assert result.dwg_quantity == 5

    def test_match_single_item_partial(self):
        """测试匹配单个项目 - 部分匹配"""
        contract_item = WorkItem(
            name="铝合金门",
            category="门窗",
            quantity=10,
            unit="套"
        )

        dwg_stats = {
            "blocks_by_category": {
                "门窗": [
                    {"name": "M1021", "count": 8}
                ]
            }
        }

        result = self.matcher._match_single_item(contract_item, dwg_stats, {})

        assert result.match_status == "partial"
        assert result.difference == -2

    def test_match_single_item_missing(self):
        """测试匹配单个项目 - 缺失"""
        contract_item = WorkItem(
            name="铝合金门",
            category="门窗",
            quantity=10,
            unit="套"
        )

        dwg_stats = {
            "blocks_by_category": {}
        }

        result = self.matcher._match_single_item(contract_item, dwg_stats, {})

        assert result.match_status == "missing"
        assert result.dwg_quantity == 0

    def test_calculate_compliance(self):
        """测试计算符合度"""
        match_results = [
            # matched
            type('Result', (), {
                'match_status': 'matched',
                'difference_percent': 0
            })(),
            # partial
            type('Result', (), {
                'match_status': 'partial',
                'difference_percent': 10
            })(),
            # missing
            type('Result', (), {
                'match_status': 'missing',
                'difference_percent': 100
            })(),
        ]

        compliance = self.matcher._calculate_compliance(match_results)

        # matched: 100, partial: 90, missing: 0
        # average: (100 + 90 + 0) / 3 = 63.33
        assert 60 < compliance < 70

    @pytest.mark.asyncio
    async def test_compare(self, sample_dxf_data):
        """测试完整比对"""
        contract_items = [
            WorkItem(name="门", category="门窗", quantity=5, unit="套"),
            WorkItem(name="窗", category="门窗", quantity=3, unit="套"),
            WorkItem(name="柱", category="土建", quantity=10, unit="个"),
        ]

        result = await self.matcher.compare(contract_items, sample_dxf_data)

        assert result.total_contract_items == 3
        assert result.overall_compliance >= 0


class TestContractAnalysisResult:
    """合同分析结果测试"""

    def test_default_values(self):
        """测试默认值"""
        result = ContractAnalysisResult()

        assert result.project_name == ""
        assert result.work_items == []
        assert result.total_amount == 0

    def test_with_work_items(self):
        """测试包含工作项"""
        items = [
            WorkItem(name="门", category="门窗", quantity=10, unit="套"),
            WorkItem(name="窗", category="门窗", quantity=20, unit="套"),
        ]

        result = ContractAnalysisResult(
            project_name="测试项目",
            work_items=items,
            total_amount=1000000
        )

        assert len(result.work_items) == 2
        assert result.total_amount == 1000000