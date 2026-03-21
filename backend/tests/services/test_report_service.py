"""
报告服务测试
"""
import pytest
import json
from app.services.report_service import (
    ReportService, ReportData, ReportIssue
)


class TestReportIssue:
    """报告问题测试"""

    def test_create_report_issue(self):
        """测试创建报告问题"""
        issue = ReportIssue(
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
        assert issue.description == "图层命名不规范"
        assert issue.location == "Layer1"
        assert issue.suggestion == "重命名图层"
        assert issue.source == "rule"
        assert issue.confidence == 1.0

    def test_report_issue_defaults(self):
        """测试报告问题默认值"""
        issue = ReportIssue(
            category="test",
            severity="warning",
            description="test description"
        )

        assert issue.location == ""
        assert issue.suggestion == ""
        assert issue.source == ""
        assert issue.confidence == 1.0


class TestReportData:
    """报告数据测试"""

    def test_create_report_data(self):
        """测试创建报告数据"""
        issues = [
            ReportIssue(
                category="图层规范",
                severity="error",
                description="图层命名不规范"
            )
        ]

        report = ReportData(
            report_id="test-123",
            created_at="2024-01-01T12:00:00",
            file_name="test.dwg",
            overall_score=85.5,
            assessment="通过",
            issues=issues,
            summary={"total_issues": 1},
            llm_enabled=False
        )

        assert report.report_id == "test-123"
        assert report.file_name == "test.dwg"
        assert report.overall_score == 85.5
        assert report.assessment == "通过"
        assert len(report.issues) == 1
        assert report.llm_enabled is False

    def test_report_data_with_contract(self):
        """测试包含合同分析的报告数据"""
        report = ReportData(
            report_id="test-456",
            created_at="2024-01-01T12:00:00",
            file_name="project.dwg",
            overall_score=90,
            assessment="通过",
            contract_analysis={
                "project_name": "测试项目",
                "work_items": [
                    {"name": "门窗", "quantity": 100}
                ]
            },
            contract_dwg_comparison={
                "overall_compliance": 95.5,
                "matched_items": 10
            }
        )

        assert report.contract_analysis is not None
        assert report.contract_analysis["project_name"] == "测试项目"
        assert report.contract_dwg_comparison is not None
        assert report.contract_dwg_comparison["overall_compliance"] == 95.5


class TestReportService:
    """报告服务测试"""

    def setup_method(self):
        self.service = ReportService()

    def test_generate_report(self):
        """测试生成报告"""
        review_result = {
            "dwg_review": {
                "overall_score": 85,
                "assessment": "通过",
                "issues": [
                    {
                        "category": "图层规范",
                        "severity": "warning",
                        "description": "图层命名不规范",
                        "location": "Layer1",
                        "suggestion": "重命名图层",
                        "source": "rule",
                        "confidence": 1.0
                    }
                ],
                "summary": {
                    "total_issues": 1,
                    "by_severity": {"error": 0, "warning": 1, "info": 0}
                },
                "llm_enabled": False
            }
        }

        report = self.service.generate_report(
            report_id="test-123",
            file_name="test.dwg",
            review_result=review_result
        )

        assert report.report_id == "test-123"
        assert report.file_name == "test.dwg"
        assert report.overall_score == 85
        assert report.assessment == "通过"
        assert len(report.issues) == 1

    def test_generate_report_with_contract(self):
        """测试生成包含合同分析的报告"""
        review_result = {
            "dwg_review": {
                "overall_score": 90,
                "assessment": "通过",
                "issues": [],
                "summary": {},
                "llm_enabled": True
            },
            "contract_analysis": {
                "project_name": "测试项目",
                "work_items": [
                    {"name": "门窗", "category": "门窗", "quantity": 100, "unit": "个"}
                ]
            },
            "contract_dwg_comparison": {
                "overall_compliance": 95,
                "matched_items": 5,
                "missing_items": 0
            }
        }

        report = self.service.generate_report(
            report_id="test-456",
            file_name="project.dwg",
            review_result=review_result
        )

        assert report.contract_analysis is not None
        assert report.contract_dwg_comparison is not None
        assert report.llm_enabled is True

    def test_to_json(self):
        """测试转换为 JSON"""
        report = ReportData(
            report_id="test-json",
            created_at="2024-01-01T12:00:00",
            file_name="test.dwg",
            overall_score=85,
            assessment="通过",
            issues=[
                ReportIssue(
                    category="图层规范",
                    severity="warning",
                    description="图层命名不规范"
                )
            ],
            summary={"total_issues": 1}
        )

        json_str = self.service.to_json(report)

        # 验证是有效的 JSON
        data = json.loads(json_str)
        assert data["report_id"] == "test-json"
        assert data["file_name"] == "test.dwg"
        assert data["overall_score"] == 85
        assert len(data["issues"]) == 1

    def test_to_dict(self):
        """测试转换为字典"""
        report = ReportData(
            report_id="test-dict",
            created_at="2024-01-01T12:00:00",
            file_name="test.dwg",
            overall_score=90,
            assessment="通过",
            issues=[]
        )

        data = self.service.to_dict(report)

        assert isinstance(data, dict)
        assert data["report_id"] == "test-dict"
        assert data["overall_score"] == 90
        assert data["issues"] == []

    def test_to_pdf_without_reportlab(self):
        """测试 PDF 生成（无 reportlab 时的回退）"""
        report = ReportData(
            report_id="test-pdf",
            created_at="2024-01-01T12:00:00",
            file_name="test.dwg",
            overall_score=85,
            assessment="通过",
            issues=[]
        )

        # 即使没有 reportlab，也应该返回一些内容
        pdf_content = self.service.to_pdf(report)
        assert pdf_content is not None
        assert len(pdf_content) > 0

    def test_generate_report_empty_issues(self):
        """测试生成无问题的报告"""
        review_result = {
            "dwg_review": {
                "overall_score": 100,
                "assessment": "通过",
                "issues": [],
                "summary": {"total_issues": 0},
                "llm_enabled": False
            }
        }

        report = self.service.generate_report(
            report_id="perfect",
            file_name="perfect.dwg",
            review_result=review_result
        )

        assert report.overall_score == 100
        assert report.assessment == "通过"
        assert len(report.issues) == 0

    def test_generate_report_multiple_issues(self):
        """测试生成多问题报告"""
        review_result = {
            "dwg_review": {
                "overall_score": 60,
                "assessment": "需修改",
                "issues": [
                    {
                        "category": "图层规范",
                        "severity": "error",
                        "description": "图层命名错误",
                        "location": "Layer1"
                    },
                    {
                        "category": "标注规范",
                        "severity": "warning",
                        "description": "标注字体过小",
                        "location": "标注层"
                    },
                    {
                        "category": "图块规范",
                        "severity": "info",
                        "description": "图块未定义属性",
                        "location": "门窗"
                    }
                ],
                "summary": {
                    "total_issues": 3,
                    "by_severity": {"error": 1, "warning": 1, "info": 1}
                },
                "llm_enabled": False
            }
        }

        report = self.service.generate_report(
            report_id="multi-issues",
            file_name="multi.dwg",
            review_result=review_result
        )

        assert len(report.issues) == 3
        assert report.issues[0].severity == "error"
        assert report.issues[1].severity == "warning"
        assert report.issues[2].severity == "info"