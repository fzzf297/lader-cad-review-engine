"""
报告生成服务 - JSON 和 PDF 报告生成
"""
from typing import Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
import json
import io
import logging

logger = logging.getLogger(__name__)


@dataclass
class ReportIssue:
    """报告中的问题项"""
    category: str
    severity: str
    description: str
    location: str = ""
    suggestion: str = ""
    source: str = ""
    confidence: float = 1.0


@dataclass
class ReportData:
    """报告数据结构"""
    report_id: str
    created_at: str
    file_name: str
    overall_score: float
    assessment: str
    issues: List[ReportIssue] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    llm_enabled: bool = False


class ReportService:
    """报告生成服务"""

    def generate_report(
        self,
        report_id: str,
        file_name: str,
        review_result: Dict[str, Any]
    ) -> ReportData:
        """生成报告数据"""

        dwg_review = review_result.get("dwg_review", {})

        issues = [
            ReportIssue(
                category=issue.get("category", ""),
                severity=issue.get("severity", ""),
                description=issue.get("description", ""),
                location=issue.get("location", ""),
                suggestion=issue.get("suggestion", ""),
                source=issue.get("source", ""),
                confidence=issue.get("confidence", 1.0)
            )
            for issue in dwg_review.get("issues", [])
        ]

        return ReportData(
            report_id=report_id,
            created_at=datetime.now().isoformat(),
            file_name=file_name,
            overall_score=dwg_review.get("overall_score", 0),
            assessment=dwg_review.get("assessment", ""),
            issues=issues,
            summary=dwg_review.get("summary", {}),
            llm_enabled=dwg_review.get("llm_enabled", False)
        )

    def to_json(self, report: ReportData) -> str:
        """转换为 JSON 格式"""
        return json.dumps(self._report_to_dict(report), ensure_ascii=False, indent=2)

    def to_dict(self, report: ReportData) -> Dict[str, Any]:
        """转换为字典格式"""
        return self._report_to_dict(report)

    def _report_to_dict(self, report: ReportData) -> Dict[str, Any]:
        """报告转字典"""
        return {
            "report_id": report.report_id,
            "created_at": report.created_at,
            "file_name": report.file_name,
            "overall_score": report.overall_score,
            "assessment": report.assessment,
            "issues": [
                {
                    "category": i.category,
                    "severity": i.severity,
                    "description": i.description,
                    "location": i.location,
                    "suggestion": i.suggestion,
                    "source": i.source,
                    "confidence": i.confidence
                }
                for i in report.issues
            ],
            "summary": report.summary,
            "llm_enabled": report.llm_enabled
        }

    def to_pdf(self, report: ReportData) -> bytes:
        """生成 PDF 报告"""
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import cm
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
        except ImportError:
            logger.warning("reportlab 未安装，使用简单 PDF 生成")
            return self._generate_simple_pdf(report)

        # 创建 PDF 文档
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )

        # 获取样式
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'Title',
            parent=styles['Heading1'],
            fontSize=18,
            spaceAfter=20
        )
        heading_style = ParagraphStyle(
            'Heading',
            parent=styles['Heading2'],
            fontSize=14,
            spaceBefore=15,
            spaceAfter=10
        )
        normal_style = styles['Normal']

        # 构建内容
        elements = []

        # 标题
        elements.append(Paragraph("DWG 施工图审核报告", title_style))
        elements.append(Spacer(1, 10))

        # 基本信息
        elements.append(Paragraph("一、基本信息", heading_style))
        info_data = [
            ["报告编号", report.report_id],
            ["生成时间", report.created_at],
            ["文件名称", report.file_name],
            ["综合评分", f"{report.overall_score:.1f} 分"],
            ["审核结论", report.assessment],
        ]
        info_table = Table(info_data, colWidths=[3*cm, 10*cm])
        info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 5),
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 15))

        # 问题汇总
        elements.append(Paragraph("二、问题汇总", heading_style))
        summary = report.summary
        if summary:
            summary_data = [
                ["问题总数", str(summary.get("total_issues", 0))],
                ["错误数", str(summary.get("by_severity", {}).get("error", 0))],
                ["警告数", str(summary.get("by_severity", {}).get("warning", 0))],
                ["提示数", str(summary.get("by_severity", {}).get("info", 0))],
            ]
            summary_table = Table(summary_data, colWidths=[3*cm, 5*cm])
            summary_table.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('PADDING', (0, 0), (-1, -1), 5),
            ]))
            elements.append(summary_table)
        elements.append(Spacer(1, 15))

        # 问题详情
        if report.issues:
            elements.append(Paragraph("三、问题详情", heading_style))

            # 问题表格
            issue_headers = ["序号", "类别", "严重程度", "问题描述", "建议"]
            issue_data = [issue_headers]

            for idx, issue in enumerate(report.issues, 1):
                issue_data.append([
                    str(idx),
                    issue.category,
                    issue.severity,
                    issue.description[:50] + "..." if len(issue.description) > 50 else issue.description,
                    issue.suggestion[:30] + "..." if len(issue.suggestion) > 30 else issue.suggestion
                ])

            issue_table = Table(issue_data, colWidths=[1*cm, 2*cm, 2*cm, 6*cm, 4*cm])
            issue_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('PADDING', (0, 0), (-1, -1), 3),
            ]))
            elements.append(issue_table)
            elements.append(Spacer(1, 15))

        # 生成 PDF
        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()

    def _generate_simple_pdf(self, report: ReportData) -> bytes:
        """生成简单的文本 PDF（当 reportlab 不可用时）"""
        try:
            from fpdf import FPDF
        except ImportError:
            # 如果连 fpdf 也没有，返回 JSON 作为 fallback
            return self.to_json(report).encode('utf-8')

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)

        # 标题
        pdf.cell(0, 10, "DWG Review Report", ln=True, align="C")
        pdf.ln(10)

        # 基本信息
        pdf.cell(0, 8, f"Report ID: {report.report_id}", ln=True)
        pdf.cell(0, 8, f"Created: {report.created_at}", ln=True)
        pdf.cell(0, 8, f"File: {report.file_name}", ln=True)
        pdf.cell(0, 8, f"Score: {report.overall_score:.1f}", ln=True)
        pdf.cell(0, 8, f"Assessment: {report.assessment}", ln=True)
        pdf.ln(10)

        # 问题列表
        pdf.cell(0, 8, f"Total Issues: {len(report.issues)}", ln=True)
        for idx, issue in enumerate(report.issues, 1):
            pdf.ln(5)
            pdf.cell(0, 6, f"{idx}. [{issue.severity}] {issue.category}", ln=True)
            pdf.multi_cell(0, 5, f"   {issue.description}")

        return pdf.output(dest='S').encode('latin-1')
