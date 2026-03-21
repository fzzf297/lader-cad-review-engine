"""
结果融合引擎测试
"""
import pytest
from app.services.result_merger import ResultMerger, MergedIssue, MergedReviewResult
from app.rules.engine import RuleResult, Issue, Severity
from app.llm.llm_service import LLMReviewResult


class TestMergedIssue:
    """融合问题测试"""

    def test_create_merged_issue(self):
        """测试创建融合问题"""
        issue = MergedIssue(
            category="图层规范",
            severity="error",
            description="图层命名不规范",
            location="Layer1",
            suggestion="重命名图层",
            source="rule",
            confidence=1.0
        )

        assert issue.category == "图层规范"
        assert issue.severity == "error"
        assert issue.source == "rule"
        assert issue.confidence == 1.0


class TestMergedReviewResult:
    """融合结果测试"""

    def test_default_values(self):
        """测试默认值"""
        result = MergedReviewResult()

        assert result.overall_score == 0
        assert result.assessment == ""
        assert result.issues == []
        assert result.llm_enabled is False

    def test_with_llm(self):
        """测试启用 LLM"""
        result = MergedReviewResult(
            overall_score=85,
            assessment="通过",
            llm_enabled=True
        )

        assert result.llm_enabled is True


class TestResultMerger:
    """结果融合引擎测试"""

    def setup_method(self):
        self.merger = ResultMerger()

    def test_merge_rule_only_results(self):
        """测试仅规则引擎结果"""
        rule_results = {
            "LAYER_001": RuleResult(
                rule_code="LAYER_001",
                rule_name="图层规范",
                rule_category="图层",
                score=90,
                issues=[
                    Issue(
                        code="LAYER_001",
                        message="图层命名不规范",
                        severity=Severity.WARNING,
                        layer="Layer1"
                    )
                ]
            )
        }

        result = self.merger.merge(rule_results, None)

        assert result.overall_score == 90
        assert result.llm_enabled is False
        assert len(result.issues) == 1
        assert result.issues[0].source == "rule"

    def test_merge_with_llm_results(self):
        """测试融合规则和 LLM 结果"""
        rule_results = {
            "LAYER_001": RuleResult(
                rule_code="LAYER_001",
                rule_name="图层规范",
                rule_category="图层",
                score=80,
                issues=[]
            )
        }

        llm_result = LLMReviewResult(
            overall_assessment="需修改",
            score=70,
            issues=[
                {
                    "category": "设计合理性",
                    "severity": "warning",
                    "description": "图纸表达不完整",
                    "suggestion": "补充详图"
                }
            ]
        )

        merged = self.merger.merge(rule_results, llm_result)

        # 评分应该是加权平均：80*0.6 + 70*0.4 = 76
        assert merged.overall_score == 76
        assert merged.llm_enabled is True

    def test_merge_duplicate_issues(self):
        """测试合并重复问题"""
        rule_results = {
            "LAYER_001": RuleResult(
                rule_code="LAYER_001",
                rule_name="图层规范",
                rule_category="图层规范",
                score=80,
                issues=[
                    Issue(
                        code="LAYER_001",
                        message="图层命名不规范",
                        severity=Severity.WARNING,
                        layer="Layer1"
                    )
                ]
            )
        }

        llm_result = LLMReviewResult(
            overall_assessment="需修改",
            score=80,
            issues=[
                {
                    "category": "图层规范",
                    "severity": "warning",
                    "description": "图层命名不规范",
                    "suggestion": "修改图层名称"
                }
            ]
        )

        merged = self.merger.merge(rule_results, llm_result)

        # 相同问题应该被标记为 "both"
        both_issues = [i for i in merged.issues if i.source == "both"]
        assert len(both_issues) >= 1
        assert both_issues[0].confidence == 1.0

    def test_severity_rank(self):
        """测试严重程度排序"""
        assert self.merger._severity_rank("error") == 0
        assert self.merger._severity_rank("warning") == 1
        assert self.merger._severity_rank("info") == 2

    def test_generate_assessment_pass(self):
        """测试生成通过评价"""
        assessment = self.merger._generate_assessment(95, [])
        assert assessment == "通过"

    def test_generate_assessment_fail(self):
        """测试生成失败评价"""
        issues = [
            MergedIssue(category="test", severity="error", description="error 1"),
            MergedIssue(category="test", severity="error", description="error 2"),
            MergedIssue(category="test", severity="error", description="error 3"),
            MergedIssue(category="test", severity="error", description="error 4"),
            MergedIssue(category="test", severity="error", description="error 5"),
            MergedIssue(category="test", severity="error", description="error 6"),
        ]

        assessment = self.merger._generate_assessment(50, issues)
        assert assessment == "不通过"

    def test_generate_summary(self):
        """测试生成摘要"""
        issues = [
            MergedIssue(category="图层", severity="error", description="e1", source="rule"),
            MergedIssue(category="图层", severity="warning", description="w1", source="llm"),
            MergedIssue(category="标注", severity="info", description="i1", source="both"),
        ]

        summary = self.merger._generate_summary(issues)

        assert summary["total_issues"] == 3
        assert summary["by_severity"]["error"] == 1
        assert summary["by_severity"]["warning"] == 1
        assert summary["by_severity"]["info"] == 1
        assert summary["by_source"]["rule_only"] == 1
        assert summary["by_source"]["llm_only"] == 1
        assert summary["by_source"]["both"] == 1

    def test_similar_text_detection(self):
        """测试相似文本检测"""
        # 相同文本
        assert self.merger._similar_text("图层命名不规范", "图层命名不规范") is True

        # 完全不同
        assert self.merger._similar_text("图层命名不规范", "尺寸标注错误") is False

        # 部分相似
        assert self.merger._similar_text("图层命名不规范", "图层名称不规范") is True