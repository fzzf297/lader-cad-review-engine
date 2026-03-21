"""
规则引擎测试
"""
import pytest
from app.rules.engine import (
    ReviewEngine,
    BaseRule,
    RuleResult,
    Issue,
    Severity,
    LayerNamingRule,
    BlockNamingRule,
    TextStyleRule,
    DimensionStyleRule,
)


class TestIssue:
    """Issue 数据类测试"""

    def test_create_issue(self):
        """测试创建问题"""
        issue = Issue(
            code="LAYER_001",
            message="图层命名不规范",
            severity=Severity.WARNING,
            layer="Layer1",
            suggestion="建议重命名"
        )

        assert issue.code == "LAYER_001"
        assert issue.message == "图层命名不规范"
        assert issue.severity == Severity.WARNING
        assert issue.layer == "Layer1"

    def test_issue_default_values(self):
        """测试问题默认值"""
        issue = Issue(
            code="TEST",
            message="Test",
            severity=Severity.INFO
        )

        assert issue.layer == ""
        assert issue.suggestion == ""
        assert issue.details == {}


class TestRuleResult:
    """RuleResult 数据类测试"""

    def test_passed_result(self):
        """测试通过的结果"""
        result = RuleResult(
            rule_code="TEST_001",
            rule_name="测试规则",
            rule_category="测试",
            score=100,
            issues=[],
            passed=True
        )

        assert result.passed is True
        assert result.score == 100

    def test_failed_result(self):
        """测试失败的结果"""
        issue = Issue(
            code="TEST_001",
            message="发现问题",
            severity=Severity.ERROR
        )

        result = RuleResult(
            rule_code="TEST_001",
            rule_name="测试规则",
            rule_category="测试",
            score=60,
            issues=[issue],
            passed=False
        )

        assert result.passed is False
        assert result.score == 60
        assert len(result.issues) == 1


class TestLayerNamingRule:
    """图层命名规则测试"""

    def setup_method(self):
        self.rule = LayerNamingRule()

    def test_rule_properties(self):
        """测试规则属性"""
        assert self.rule.code == "LAYER_001"
        assert self.rule.name == "图层命名规范"
        assert self.rule.category == "图层规范"

    def test_check_empty_layers(self):
        """测试空图层"""
        dxf_data = {"layers": {}}
        result = self.rule.check(dxf_data)

        assert result.score == 100
        assert len(result.issues) == 0

    def test_check_standard_layer_names(self, sample_dxf_data):
        """测试标准图层名称"""
        dxf_data = {"layers": sample_dxf_data["layers"]}
        # 移除非标准图层
        dxf_data["layers"].pop("Layer1", None)

        result = self.rule.check(dxf_data)

        # 应该没有错误（标准名称）
        error_issues = [i for i in result.issues if i.severity == Severity.ERROR]
        assert len(error_issues) == 0

    def test_check_invalid_layer_names(self):
        """测试不规范的图层名称"""
        dxf_data = {
            "layers": {
                "Layer1": {"name": "Layer1"},
                "图层1": {"name": "图层1"},
                "123": {"name": "123"},
                "墙体": {"name": "墙体"},
            }
        }

        result = self.rule.check(dxf_data)

        # "Layer1"、"图层1"、"123" 应该被标记
        assert len(result.issues) >= 2


class TestBlockNamingRule:
    """图块命名规则测试"""

    def setup_method(self):
        self.rule = BlockNamingRule()

    def test_rule_properties(self):
        """测试规则属性"""
        assert self.rule.code == "BLOCK_001"
        assert self.rule.name == "图块命名规范"

    def test_check_standard_door_window_blocks(self, sample_dxf_data):
        """测试标准门窗图块命名"""
        result = self.rule.check(sample_dxf_data)

        # M1021、C1515 是标准命名
        assert result.score >= 80

    def test_check_non_standard_blocks(self):
        """测试非标准图块命名"""
        dxf_data = {
            "blocks": {
                "door_block_01": {
                    "name": "door_block_01",
                    "is_door_window": True,
                    "insert_count": 5
                },
                "window_test": {
                    "name": "window_test",
                    "is_door_window": True,
                    "insert_count": 3
                },
                "COLUMN": {
                    "name": "COLUMN",
                    "is_door_window": False,
                    "insert_count": 10
                }
            }
        }

        result = self.rule.check(dxf_data)

        # door_block_01、window_test 命名不规范
        assert len(result.issues) >= 2


class TestTextStyleRule:
    """文字样式规则测试"""

    def setup_method(self):
        self.rule = TextStyleRule()

    def test_check_empty_texts(self):
        """测试无文字"""
        dxf_data = {"texts": []}
        result = self.rule.check(dxf_data)

        assert result.score == 100

    def test_check_valid_text_height(self):
        """测试有效的文字高度"""
        dxf_data = {
            "texts": [
                {"height": 3.5, "layer": "标注"},
                {"height": 5.0, "layer": "标注"},
                {"height": 7.0, "layer": "标注"},
            ]
        }

        result = self.rule.check(dxf_data)

        # 高度都 >= 2.5，应该没有警告
        warning_issues = [i for i in result.issues if i.severity == Severity.WARNING]
        assert len(warning_issues) == 0

    def test_check_small_text_height(self):
        """测试过小的文字高度"""
        dxf_data = {
            "texts": [
                {"height": 1.0, "layer": "标注"},
                {"height": 2.0, "layer": "标注"},
                {"height": 3.5, "layer": "标注"},
            ]
        }

        result = self.rule.check(dxf_data)

        # 1.0 和 2.0 应该有警告
        warning_issues = [i for i in result.issues if i.severity == Severity.WARNING]
        assert len(warning_issues) >= 2


class TestDimensionStyleRule:
    """尺寸标注规则测试"""

    def setup_method(self):
        self.rule = DimensionStyleRule()

    def test_check_single_style(self):
        """测试单一标注样式"""
        dxf_data = {
            "dimensions": [
                {"style": "Standard"},
                {"style": "Standard"},
                {"style": "Standard"},
            ]
        }

        result = self.rule.check(dxf_data)

        assert result.score == 100

    def test_check_multiple_styles(self):
        """测试多种标注样式"""
        dxf_data = {
            "dimensions": [
                {"style": "Standard"},
                {"style": "Style1"},
                {"style": "Style2"},
                {"style": "Style3"},
            ]
        }

        result = self.rule.check(dxf_data)

        # 多种样式应该有警告
        assert result.score < 100


class TestReviewEngine:
    """规则引擎测试"""

    def setup_method(self):
        self.engine = ReviewEngine()

    def test_default_rules_registered(self):
        """测试默认规则已注册"""
        assert "LAYER_001" in self.engine.rules
        assert "BLOCK_001" in self.engine.rules
        assert "TEXT_001" in self.engine.rules

    def test_review_with_all_rules(self, sample_dxf_data):
        """测试执行所有规则"""
        results = self.engine.review(sample_dxf_data)

        assert len(results) > 0
        assert all(isinstance(r, RuleResult) for r in results.values())

    def test_review_with_specific_rules(self, sample_dxf_data):
        """测试执行特定规则"""
        results = self.engine.review(
            sample_dxf_data,
            rule_codes=["LAYER_001", "BLOCK_001"]
        )

        assert len(results) == 2
        assert "LAYER_001" in results
        assert "BLOCK_001" in results

    def test_get_overall_score(self, sample_dxf_data):
        """测试计算总体评分"""
        results = self.engine.review(sample_dxf_data)
        score = self.engine.get_overall_score(results)

        assert 0 <= score <= 100

    def test_register_custom_rule(self):
        """测试注册自定义规则"""
        class CustomRule(BaseRule):
            code = "CUSTOM_001"
            name = "自定义规则"
            category = "自定义"

            def check(self, dxf_data):
                return self._create_result(100, [], "OK")

        self.engine.register_rule(CustomRule())

        assert "CUSTOM_001" in self.engine.rules
        assert self.engine.rules["CUSTOM_001"].name == "自定义规则"