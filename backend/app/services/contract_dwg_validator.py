"""
合同-图纸对比验证服务 - 对比合同施工范围与图纸内容
"""
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
import re
import logging
from datetime import datetime

from ..parsers.dxf_parser import DxfParseResult
from ..services.review_service import ContractAnalysisResult, WorkItem
from ..services.dwg_translator import DwgContentTranslator

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """匹配结果"""
    contract_item_name: str
    contract_category: str
    contract_quantity: float
    contract_unit: str
    dwg_items: List[Dict[str, Any]] = field(default_factory=list)
    dwg_total_quantity: int = 0
    match_status: str = "unknown"  # matched, partial, missing, extra
    difference: int = 0
    difference_percent: float = 0.0
    notes: str = ""


@dataclass
class ValidationReport:
    """验证报告"""
    overall_match: float = 0.0  # 整体匹配度 0-100
    status: str = ""  # 完全匹配, 部分匹配, 不匹配
    matches: List[Dict[str, Any]] = field(default_factory=list)
    mismatches: List[Dict[str, Any]] = field(default_factory=list)
    extra_in_dwg: List[Dict[str, Any]] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    suggestions: List[str] = field(default_factory=list)


class ContractDwgValidator:
    """
    合同-图纸对比验证器

    对比合同中的施工范围与图纸中识别的内容，
    生成详细的匹配报告。
    """

    # 施工项分类映射（合同 -> 图纸）
    CATEGORY_MAPPINGS = {
        "门": ["door", "门"],
        "窗": ["window", "窗"],
        "门窗": ["door", "window", "门", "窗"],
        "地面": ["floor", "地面"],
        "墙面": ["wall", "墙面"],
        "天花": ["ceiling", "吊顶"],
        "电气": ["electrical", "电气"],
        "管道": ["pipe", "管道"],
        "消防": ["fire", "消防"],
    }

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.translator = DwgContentTranslator()

    async def validate(
        self,
        contract_result: ContractAnalysisResult,
        dxf_result: DxfParseResult,
        contract_filename: str = "",
        dwg_filename: str = ""
    ) -> ValidationReport:
        """
        执行合同-图纸对比验证

        Args:
            contract_result: 合同分析结果
            dxf_result: DXF 解析结果
            contract_filename: 合同文件名
            dwg_filename: 图纸文件名

        Returns:
            ValidationReport: 验证报告
        """
        logger.info("[合同-图纸验证] 开始对比验证...")
        logger.info(f"[合同-图纸验证] 合同: {contract_filename}, 图纸: {dwg_filename}")

        # 翻译图纸内容为施工内容
        dwg_content = self.translator.translate(dxf_result)
        logger.info(f"[合同-图纸验证] 图纸翻译完成: {dwg_content['summary']}")

        # 执行对比
        match_results = self._compare_items(contract_result.work_items, dwg_content)

        # 生成报告
        report = self._generate_report(match_results, dwg_content)

        logger.info(f"[合同-图纸验证] 验证完成，整体匹配度: {report.overall_match:.1f}%")

        return report

    def _compare_items(
        self,
        contract_items: List[WorkItem],
        dwg_content: Dict[str, Any]
    ) -> List[MatchResult]:
        """对比合同项与图纸内容"""
        results = []

        # 获取图纸中的门和窗
        dwg_doors = {item["code"]: item for item in dwg_content.get("doors", [])}
        dwg_windows = {item["code"]: item for item in dwg_content.get("windows", [])}

        # 跟踪已匹配的图纸项
        matched_dwg_doors = set()
        matched_dwg_windows = set()

        for contract_item in contract_items:
            item_name = contract_item.name
            item_category = contract_item.category
            item_qty = contract_item.quantity

            # 尝试从合同项名称提取门窗代码
            door_codes = self._extract_door_codes(item_name)
            window_codes = self._extract_window_codes(item_name)

            matched_items = []
            dwg_total = 0

            # 匹配门
            for code in door_codes:
                if code in dwg_doors:
                    matched_items.append(dwg_doors[code])
                    matched_dwg_doors.add(code)
                    dwg_total += dwg_doors[code]["count"]

            # 匹配窗
            for code in window_codes:
                if code in dwg_windows:
                    matched_items.append(dwg_windows[code])
                    matched_dwg_windows.add(code)
                    dwg_total += dwg_windows[code]["count"]

            # 如果没有直接匹配，尝试模糊匹配
            if not matched_items:
                matched_items, dwg_total = self._fuzzy_match(
                    item_name, item_category, dwg_doors, dwg_windows
                )
                for item in matched_items:
                    if item["type"] == "door":
                        matched_dwg_doors.add(item["code"])
                    elif item["type"] == "window":
                        matched_dwg_windows.add(item["code"])

            # 计算匹配状态
            match_status, diff, diff_pct = self._calculate_match_status(
                item_qty, dwg_total
            )

            # 生成备注
            notes = self._generate_notes(contract_item, matched_items, match_status)

            results.append(MatchResult(
                contract_item_name=item_name,
                contract_category=item_category,
                contract_quantity=item_qty,
                contract_unit=contract_item.unit,
                dwg_items=matched_items,
                dwg_total_quantity=dwg_total,
                match_status=match_status,
                difference=diff,
                difference_percent=diff_pct,
                notes=notes
            ))

        # 找出图纸中未匹配的项目（额外项）
        extra_doors = [
            door for code, door in dwg_doors.items()
            if code not in matched_dwg_doors
        ]
        extra_windows = [
            window for code, window in dwg_windows.items()
            if code not in matched_dwg_windows
        ]

        # 添加额外项到结果
        for extra in extra_doors:
            results.append(MatchResult(
                contract_item_name="",
                contract_category="门窗",
                contract_quantity=0,
                contract_unit="个",
                dwg_items=[extra],
                dwg_total_quantity=extra["count"],
                match_status="extra",
                difference=extra["count"],
                difference_percent=100.0,
                notes="图纸中包含此项，但合同未提及"
            ))

        for extra in extra_windows:
            results.append(MatchResult(
                contract_item_name="",
                contract_category="门窗",
                contract_quantity=0,
                contract_unit="个",
                dwg_items=[extra],
                dwg_total_quantity=extra["count"],
                match_status="extra",
                difference=extra["count"],
                difference_percent=100.0,
                notes="图纸中包含此项，但合同未提及"
            ))

        return results

    def _extract_door_codes(self, text: str) -> List[str]:
        """从文本中提取门代码"""
        codes = []
        # 匹配 M1021, FM1021, GM0921 等格式
        patterns = [
            r'(FM\d{2,4})',
            r'(GM\d{2,4})',
            r'(MM\d{2,4})',
            r'(LM\d{2,4})',
            r'(DM\d{2,4})',
            r'(TLM\d{2,4})',
            r'(ZM\d{2,4})',
            r'(JC\d{2,4})',
            r'[^A-Z](M\d{2,4})[^0-9]',  # M1021, 但避免匹配 AM1021
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text.upper())
            codes.extend(matches)
        return list(set(codes))

    def _extract_window_codes(self, text: str) -> List[str]:
        """从文本中提取窗代码"""
        codes = []
        # 匹配 C1515, GC1515, LC1515 等格式
        patterns = [
            r'(GC\d{2,4})',
            r'(LC\d{2,4})',
            r'(SC\d{2,4})',
            r'(TC\d{2,4})',
            r'(BC\d{2,4})',
            r'(ZJC\d{2,4})',
            r'(SJC\d{2,4})',
            r'(XJC\d{2,4})',
            r'[^A-Z](C\d{2,4})[^0-9]',  # C1515, 但避免匹配 AC1515
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text.upper())
            codes.extend(matches)
        return list(set(codes))

    def _fuzzy_match(
        self,
        item_name: str,
        item_category: str,
        dwg_doors: Dict[str, Dict],
        dwg_windows: Dict[str, Dict]
    ) -> Tuple[List[Dict], int]:
        """模糊匹配合同项与图纸项"""
        matched = []
        total = 0

        name_upper = item_name.upper()

        # 根据关键词匹配
        if any(kw in name_upper for kw in ["门", "DOOR", "M", "门扇"]):
            for code, door in dwg_doors.items():
                # 检查是否有共同的关键词
                if self._has_common_keyword(item_name, door["name"]):
                    matched.append(door)
                    total += door["count"]

        if any(kw in name_upper for kw in ["窗", "WINDOW", "C", "窗户"]):
            for code, window in dwg_windows.items():
                if self._has_common_keyword(item_name, window["name"]):
                    matched.append(window)
                    total += window["count"]

        return matched, total

    def _has_common_keyword(self, text1: str, text2: str) -> bool:
        """检查两个文本是否有共同的关键词"""
        keywords = ["铝合金", "塑钢", "钢质", "木质", "防火", "防盗", "推拉", "百叶"]
        text1_keywords = {kw for kw in keywords if kw in text1}
        text2_keywords = {kw for kw in keywords if kw in text2}
        return bool(text1_keywords & text2_keywords)

    def _calculate_match_status(
        self,
        contract_qty: float,
        dwg_qty: int
    ) -> Tuple[str, int, float]:
        """计算匹配状态"""
        if contract_qty == 0 and dwg_qty == 0:
            return "unknown", 0, 0.0

        if contract_qty == 0:
            return "extra", dwg_qty, 100.0

        if dwg_qty == 0:
            return "missing", -int(contract_qty), -100.0

        diff = dwg_qty - int(contract_qty)
        diff_pct = (diff / contract_qty) * 100

        # 允许 5% 的误差
        if abs(diff_pct) <= 5:
            return "matched", diff, diff_pct
        elif abs(diff_pct) <= 20:
            return "partial", diff, diff_pct
        else:
            return "mismatch", diff, diff_pct

    def _generate_notes(
        self,
        contract_item: WorkItem,
        matched_items: List[Dict],
        match_status: str
    ) -> str:
        """生成匹配备注"""
        if match_status == "matched":
            return "✅ 合同与图纸数量匹配"
        elif match_status == "partial":
            return f"⚠️ 数量有差异，合同: {contract_item.quantity}，图纸: {sum(i['count'] for i in matched_items)}"
        elif match_status == "mismatch":
            return f"❌ 数量不匹配，合同: {contract_item.quantity}，图纸: {sum(i['count'] for i in matched_items) if matched_items else 0}"
        elif match_status == "missing":
            return "❌ 图纸中未找到此项"
        elif match_status == "extra":
            return "ℹ️ 图纸中包含此项，但合同未提及"
        return ""

    def _generate_report(
        self,
        match_results: List[MatchResult],
        dwg_content: Dict[str, Any]
    ) -> ValidationReport:
        """生成验证报告"""
        matches = []
        mismatches = []
        extra_items = []

        total_items = 0
        matched_count = 0
        partial_count = 0
        missing_count = 0
        extra_count = 0

        for result in match_results:
            item_data = {
                "contract_item": result.contract_item_name,
                "contract_category": result.contract_category,
                "contract_qty": result.contract_quantity,
                "contract_unit": result.contract_unit,
                "dwg_items": [f"{i['name']}({i['code']}) x{i['count']}" for i in result.dwg_items],
                "dwg_qty": result.dwg_total_quantity,
                "status": result.match_status,
                "difference": result.difference,
                "difference_percent": round(result.difference_percent, 1),
                "notes": result.notes,
            }

            if result.match_status == "matched":
                matches.append(item_data)
                matched_count += 1
            elif result.match_status == "partial":
                matches.append(item_data)  # 部分匹配也放在 matches 中
                partial_count += 1
            elif result.match_status in ["mismatch", "missing"]:
                mismatches.append(item_data)
                missing_count += 1
            elif result.match_status == "extra":
                extra_items.append({
                    "item": result.dwg_items[0]["name"] if result.dwg_items else "",
                    "code": result.dwg_items[0]["code"] if result.dwg_items else "",
                    "dwg_qty": result.dwg_total_quantity,
                    "note": result.notes,
                })
                extra_count += 1

            if result.match_status != "extra":
                total_items += 1

        # 计算整体匹配度
        if total_items > 0:
            overall_match = ((matched_count + partial_count * 0.5) / total_items) * 100
        else:
            overall_match = 0.0

        # 确定状态
        if overall_match >= 90:
            status = "完全匹配"
        elif overall_match >= 70:
            status = "基本匹配"
        elif overall_match >= 50:
            status = "部分匹配"
        else:
            status = "匹配度较低"

        # 生成建议
        suggestions = self._generate_suggestions(match_results, mismatches)

        return ValidationReport(
            overall_match=round(overall_match, 1),
            status=status,
            matches=matches,
            mismatches=mismatches,
            extra_in_dwg=extra_items,
            summary={
                "total_contract_items": total_items,
                "matched": matched_count,
                "partial": partial_count,
                "missing": missing_count,
                "extra": extra_count,
                "total_doors": dwg_content["summary"].get("total_doors", 0),
                "total_windows": dwg_content["summary"].get("total_windows", 0),
            },
            suggestions=suggestions
        )

    def _generate_suggestions(
        self,
        match_results: List[MatchResult],
        mismatches: List[Dict]
    ) -> List[str]:
        """生成改进建议"""
        suggestions = []

        # 检查缺失项
        missing_items = [r for r in match_results if r.match_status == "missing"]
        if missing_items:
            suggestions.append(
                f"图纸中未找到 {len(missing_items)} 项合同内容，请检查图纸是否完整"
            )

        # 检查数量差异大的项
        large_diff = [
            r for r in match_results
            if r.match_status in ["mismatch", "partial"]
            and abs(r.difference_percent) > 30
        ]
        if large_diff:
            suggestions.append(
                f"发现 {len(large_diff)} 项数量差异较大（超过30%），建议核实"
            )

        # 检查额外项
        extra_items = [r for r in match_results if r.match_status == "extra"]
        if extra_items:
            suggestions.append(
                f"图纸中包含 {len(extra_items)} 项合同未提及的内容，请确认是否为增项"
            )

        if not suggestions:
            suggestions.append("合同与图纸匹配度良好，未发现明显问题")

        return suggestions

    def to_dict(self, report: ValidationReport) -> Dict[str, Any]:
        """将报告转换为字典"""
        return {
            "overall_match": report.overall_match,
            "status": report.status,
            "matches": report.matches,
            "mismatches": report.mismatches,
            "extra_in_dwg": report.extra_in_dwg,
            "summary": report.summary,
            "suggestions": report.suggestions,
            "validation_time": datetime.now().isoformat(),
        }
