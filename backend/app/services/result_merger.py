"""
结果融合引擎 - 合并规则引擎和 LLM 的审核结果
"""
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
import logging

from ..rules.engine import RuleResult, Issue, Severity
from ..llm.llm_service import LLMReviewResult

logger = logging.getLogger(__name__)


@dataclass
class MergedIssue:
    """融合后的问题"""
    category: str
    severity: str  # error, warning, info
    description: str
    location: str = ""
    suggestion: str = ""
    source: str = ""  # rule, llm, both
    confidence: float = 1.0
    rule_code: str = ""


@dataclass
class MergedReviewResult:
    """融合后的审核结果"""
    overall_score: float = 0
    assessment: str = ""
    issues: List[MergedIssue] = field(default_factory=list)
    rule_results: Dict[str, RuleResult] = field(default_factory=dict)
    llm_result: Optional[LLMReviewResult] = None
    summary: Dict[str, Any] = field(default_factory=dict)
    llm_enabled: bool = False


class ResultMerger:
    """结果融合引擎"""

    def merge(
        self,
        rule_results: Dict[str, RuleResult],
        llm_result: Optional[LLMReviewResult] = None
    ) -> MergedReviewResult:
        """融合规则引擎和 LLM 的审核结果"""

        # 收集所有问题
        all_issues: List[MergedIssue] = []

        # 添加规则引擎问题
        for rule_code, result in rule_results.items():
            for issue in result.issues:
                all_issues.append(MergedIssue(
                    category=result.rule_category,
                    severity=issue.severity.value,
                    description=issue.message,
                    location=issue.layer,
                    suggestion=issue.suggestion,
                    source="rule",
                    confidence=1.0,
                    rule_code=rule_code
                ))

        # 添加 LLM 问题
        if llm_result:
            for issue in llm_result.issues:
                llm_issue = MergedIssue(
                    category=issue.get("category", "其他"),
                    severity=issue.get("severity", "warning"),
                    description=issue.get("description", ""),
                    location=issue.get("location", ""),
                    suggestion=issue.get("suggestion", ""),
                    source="llm",
                    confidence=issue.get("confidence", 0.8)
                )

                # 检查是否与规则引擎问题重复
                if self._is_duplicate(llm_issue, all_issues):
                    # 标记为双方都发现的问题
                    self._mark_as_both(llm_issue, all_issues)
                else:
                    all_issues.append(llm_issue)

        # 计算综合评分
        overall_score = self._calculate_score(rule_results, llm_result)

        # 生成整体评价
        assessment = self._generate_assessment(overall_score, all_issues)

        # 生成摘要
        summary = self._generate_summary(all_issues)

        return MergedReviewResult(
            overall_score=overall_score,
            assessment=assessment,
            issues=sorted(all_issues, key=lambda x: self._severity_rank(x.severity)),
            rule_results=rule_results,
            llm_result=llm_result,
            summary=summary,
            llm_enabled=llm_result is not None
        )

    def _is_duplicate(self, new_issue: MergedIssue, existing: List[MergedIssue]) -> bool:
        """检查是否重复"""
        for issue in existing:
            if issue.category == new_issue.category:
                if self._similar_text(issue.description, new_issue.description):
                    return True
        return False

    def _similar_text(self, text1: str, text2: str, threshold: float = 0.5) -> bool:
        """简单的文本相似度判断，支持中文"""
        # 对于中文，按字符比较
        if all('\u4e00' <= c <= '\u9fff' or c.isspace() for c in text1 + text2):
            chars1 = set(text1)
            chars2 = set(text2)
            if not chars1 or not chars2:
                return False
            intersection = len(chars1 & chars2)
            union = len(chars1 | chars2)
            return intersection / union > threshold if union > 0 else False

        # 对于其他文本，按单词比较
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        if not words1 or not words2:
            return False
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        return intersection / union > threshold if union > 0 else False

    def _mark_as_both(self, llm_issue: MergedIssue, issues: List[MergedIssue]):
        """标记为双方都发现的问题"""
        for issue in issues:
            if issue.category == llm_issue.category:
                if self._similar_text(issue.description, llm_issue.description):
                    issue.source = "both"
                    issue.confidence = 1.0
                    break

    def _calculate_score(
        self,
        rule_results: Dict[str, RuleResult],
        llm_result: Optional[LLMReviewResult]
    ) -> float:
        """计算综合评分"""
        # 规则引擎权重 60%，LLM 权重 40%
        if not rule_results:
            rule_score = 100
        else:
            rule_score = sum(r.score for r in rule_results.values()) / len(rule_results)

        if llm_result:
            llm_score = llm_result.score
            return rule_score * 0.6 + llm_score * 0.4
        else:
            return rule_score

    def _severity_rank(self, severity: str) -> int:
        """问题严重程度排序"""
        ranks = {"error": 0, "warning": 1, "info": 2}
        return ranks.get(severity, 3)

    def _generate_assessment(self, score: float, issues: List[MergedIssue]) -> str:
        """生成整体评价"""
        error_count = sum(1 for i in issues if i.severity == "error")
        warning_count = sum(1 for i in issues if i.severity == "warning")

        if error_count == 0 and warning_count == 0:
            return "通过"
        elif error_count > 5 or score < 60:
            return "不通过"
        else:
            return "需修改"

    def _generate_summary(self, issues: List[MergedIssue]) -> Dict[str, Any]:
        """生成问题摘要"""
        return {
            "total_issues": len(issues),
            "by_severity": {
                "error": sum(1 for i in issues if i.severity == "error"),
                "warning": sum(1 for i in issues if i.severity == "warning"),
                "info": sum(1 for i in issues if i.severity == "info"),
            },
            "by_source": {
                "rule_only": sum(1 for i in issues if i.source == "rule"),
                "llm_only": sum(1 for i in issues if i.source == "llm"),
                "both": sum(1 for i in issues if i.source == "both"),
            },
            "by_category": self._group_by_category(issues)
        }

    def _group_by_category(self, issues: List[MergedIssue]) -> Dict[str, int]:
        """按类别分组"""
        result = {}
        for issue in issues:
            result[issue.category] = result.get(issue.category, 0) + 1
        return result