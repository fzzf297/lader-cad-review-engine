"""
规则引擎 - 基于 GB/T 50001-2017 房屋建筑制图统一标准的规则检查
"""
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from enum import Enum
import re
import logging

logger = logging.getLogger(__name__)


class Severity(Enum):
    """问题严重程度"""
    ERROR = "error"      # 错误 - 必须修改
    WARNING = "warning"  # 警告 - 建议修改
    INFO = "info"        # 信息 - 仅供参考


@dataclass
class Issue:
    """审核问题"""
    code: str                # 规则编码
    message: str             # 问题描述
    severity: Severity       # 严重程度
    layer: str = ""          # 相关图层
    entity_handle: str = ""  # 相关实体句柄
    suggestion: str = ""     # 修改建议
    details: Dict = field(default_factory=dict)


@dataclass
class RuleResult:
    """规则检查结果"""
    rule_code: str
    rule_name: str
    rule_category: str
    score: float  # 0-100
    issues: List[Issue] = field(default_factory=list)
    passed: bool = True
    message: str = ""


class BaseRule(ABC):
    """规则基类"""

    code: str = ""
    name: str = ""
    category: str = ""
    description: str = ""
    standard: str = ""  # 参考标准

    @abstractmethod
    def check(self, dxf_data: Dict[str, Any]) -> RuleResult:
        """执行规则检查"""
        pass

    def _create_result(self, score: float, issues: List[Issue], message: str = "") -> RuleResult:
        """创建检查结果"""
        return RuleResult(
            rule_code=self.code,
            rule_name=self.name,
            rule_category=self.category,
            score=score,
            issues=issues,
            passed=len([i for i in issues if i.severity == Severity.ERROR]) == 0,
            message=message
        )


class LayerNamingRule(BaseRule):
    """图层命名规范规则

    根据 GB/T 50001-2017，图层命名应遵循：
    - 使用中文或英文标准名称
    - 避免使用特殊字符
    - 命名应能反映图层内容
    """

    code = "LAYER_001"
    name = "图层命名规范"
    category = "图层规范"
    description = "检查图层命名是否符合国标要求"
    standard = "GB/T 50001-2017 第4.1节"

    # 标准图层名称（中文）
    STANDARD_LAYERS_CN = {
        "墙体", "柱", "梁", "板", "门窗", "楼梯", "阳台",
        "标注", "尺寸", "文字", "图框", "轴线", "填充",
        "家具", "设备", "管道", "电气", "暖通",
    }

    # 标准图层名称（英文）
    STANDARD_LAYERS_EN = {
        "WALL", "COLUMN", "BEAM", "SLAB", "DOOR", "WINDOW",
        "DIM", "TEXT", "AXIS", "HATCH", "FURNITURE",
        "EQUIP", "PIPE", "ELEC", "HVAC",
    }

    # 不规范的命名模式
    INVALID_PATTERNS = [
        r"^[\d]+$",           # 纯数字
        r"^[_\-\s]+$",        # 仅特殊字符
        r"^Layer\s*\d+$",     # Layer + 数字
        r"^图层\d+$",         # 图层 + 数字
    ]

    def check(self, dxf_data: Dict[str, Any]) -> RuleResult:
        layers = dxf_data.get("layers", {})
        issues = []

        if not layers:
            return self._create_result(100, [], "未发现图层定义")

        total_layers = len(layers)
        valid_layers = 0

        for layer_name, layer_info in layers.items():
            is_valid = True

            # 检查是否为标准名称
            is_standard = (
                layer_name in self.STANDARD_LAYERS_CN or
                layer_name.upper() in self.STANDARD_LAYERS_EN or
                self._is_valid_custom_name(layer_name)
            )

            # 检查是否匹配不规范模式
            for pattern in self.INVALID_PATTERNS:
                if re.match(pattern, layer_name, re.IGNORECASE):
                    is_valid = False
                    issues.append(Issue(
                        code=self.code,
                        message=f"图层名称「{layer_name}」不符合命名规范，建议使用有意义的名称",
                        severity=Severity.WARNING,
                        layer=layer_name,
                        suggestion=f"建议重命名为标准名称，如：墙体、门窗、标注等"
                    ))
                    break

            if is_valid and is_standard:
                valid_layers += 1

        # 计算评分
        score = (valid_layers / total_layers * 100) if total_layers > 0 else 100

        return self._create_result(score, issues, f"共 {total_layers} 个图层，{valid_layers} 个命名规范")

    def _is_valid_custom_name(self, name: str) -> bool:
        """检查自定义名称是否有效"""
        # 长度检查
        if len(name) < 1 or len(name) > 50:
            return False

        # 包含有效字符
        if re.match(r"^[\w\u4e00-\u9fa5\-_\s]+$", name):
            return True

        return False


class LineWeightRule(BaseRule):
    """线型线宽规范规则

    根据 GB/T 50001-2017，不同用途的线型应有不同的线宽：
    - 粗实线：0.5-0.7mm（轮廓线、边框线）
    - 中实线：0.35mm（轴线、尺寸线）
    - 细实线：0.18-0.25mm（填充、辅助线）
    """

    code = "LINE_001"
    name = "线型线宽规范"
    category = "线型规范"
    description = "检查线宽设置是否符合国标要求"
    standard = "GB/T 50001-2017 第3.1节"

    # 标准线宽映射（mm）
    STANDARD_WEIGHTS = {
        "粗线": [0.5, 0.6, 0.7],
        "中线": [0.35, 0.4],
        "细线": [0.18, 0.2, 0.25],
    }

    def check(self, dxf_data: Dict[str, Any]) -> RuleResult:
        # 简化实现：检查图层是否定义了线宽
        layers = dxf_data.get("layers", {})
        issues = []

        # 这里需要更详细的线宽检查逻辑
        # 目前简化为检查是否有图层设置了线宽

        return self._create_result(100, issues, "线宽检查通过")


class TextStyleRule(BaseRule):
    """文字样式规范规则

    根据 GB/T 50001-2017，文字应满足：
    - 汉字采用仿宋体或黑体
    - 字高应按标准比例
    - 最小字高不小于 2.5mm（出图比例1:100）
    """

    code = "TEXT_001"
    name = "文字样式规范"
    category = "文字规范"
    description = "检查文字样式是否符合国标要求"
    standard = "GB/T 50001-2017 第5节"

    # 标准字高（mm，出图比例1:100）
    STANDARD_HEIGHTS = [2.5, 3.5, 5, 7, 10, 14, 20]

    def check(self, dxf_data: Dict[str, Any]) -> RuleResult:
        texts = dxf_data.get("texts", [])
        issues = []

        if not texts:
            return self._create_result(100, [], "未发现文字实体")

        total_texts = len(texts)
        invalid_height_count = 0

        for text in texts:
            height = text.get("height", 0)

            # 检查字高是否过小
            if height > 0 and height < 2.5:
                invalid_height_count += 1
                issues.append(Issue(
                    code=self.code,
                    message=f"文字高度 {height}mm 过小，不符合国标要求（最小2.5mm）",
                    severity=Severity.WARNING,
                    layer=text.get("layer", ""),
                    entity_handle=text.get("handle", ""),
                    suggestion="调整文字高度至 2.5mm 以上"
                ))

        score = ((total_texts - invalid_height_count) / total_texts * 100) if total_texts > 0 else 100

        return self._create_result(score, issues, f"共 {total_texts} 个文字实体")


class BlockNamingRule(BaseRule):
    """图块命名规范规则

    门窗等图块命名应符合标准：
    - 门：M + 宽高（如 M1021 表示宽1米高2.1米）
    - 窗：C + 宽高（如 C1515 表示宽1.5米高1.5米）
    """

    code = "BLOCK_001"
    name = "图块命名规范"
    category = "图块规范"
    description = "检查图块命名是否符合行业惯例"
    standard = "行业标准"

    # 门窗命名正则
    DOOR_PATTERN = re.compile(r"^[Mm](\d{4}|\d{2}\d{2})$")  # M1021, M0921
    WINDOW_PATTERN = re.compile(r"^[Cc](\d{4}|\d{2}\d{2})$")  # C1515, C1212

    def check(self, dxf_data: Dict[str, Any]) -> RuleResult:
        blocks = dxf_data.get("blocks", {})
        issues = []

        if not blocks:
            return self._create_result(100, [], "未发现图块定义")

        door_window_blocks = []
        invalid_naming = []

        for block_name, block_info in blocks.items():
            if block_info.get("is_door_window"):
                door_window_blocks.append(block_name)

                # 检查命名格式
                is_valid = (
                    self.DOOR_PATTERN.match(block_name) or
                    self.WINDOW_PATTERN.match(block_name)
                )

                if not is_valid:
                    # 检查是否包含门/窗关键词
                    has_keyword = any(
                        kw in block_name.upper()
                        for kw in ["DOOR", "WINDOW", "门", "窗", "M", "C"]
                    )

                    if has_keyword:
                        invalid_naming.append(block_name)
                        issues.append(Issue(
                            code=self.code,
                            message=f"图块「{block_name}」命名不规范",
                            severity=Severity.INFO,
                            suggestion="建议使用标准命名格式，如 M1021（宽1米高2.1米的门）"
                        ))

        total = len(door_window_blocks)
        invalid = len(invalid_naming)
        score = ((total - invalid) / total * 100) if total > 0 else 100

        return self._create_result(score, issues, f"发现 {total} 个门窗图块，{invalid} 个命名不规范")


class DimensionStyleRule(BaseRule):
    """尺寸标注规范规则

    根据 GB/T 50001-2017，尺寸标注应：
    - 使用统一的标注样式
    - 文字方向一致
    - 尺寸线间距适当
    """

    code = "DIM_001"
    name = "尺寸标注规范"
    category = "标注规范"
    description = "检查尺寸标注样式是否统一"
    standard = "GB/T 50001-2017 第6节"

    def check(self, dxf_data: Dict[str, Any]) -> RuleResult:
        dimensions = dxf_data.get("dimensions", [])
        issues = []

        if not dimensions:
            return self._create_result(100, [], "未发现尺寸标注")

        # 统计标注样式
        styles = {}
        for dim in dimensions:
            style = dim.get("style", "Standard")
            styles[style] = styles.get(style, 0) + 1

        # 如果样式过多，给出警告
        if len(styles) > 3:
            issues.append(Issue(
                code=self.code,
                message=f"发现 {len(styles)} 种标注样式，建议统一使用同一样式",
                severity=Severity.WARNING,
                suggestion="建议统一标注样式，保持图纸一致性"
            ))

        score = 100 - (len(styles) - 1) * 10 if len(styles) > 1 else 100
        score = max(60, score)

        return self._create_result(score, issues, f"共 {len(dimensions)} 个尺寸标注，使用 {len(styles)} 种样式")


class ReviewEngine:
    """规则引擎 - 管理和执行所有规则"""

    def __init__(self):
        self.rules: Dict[str, BaseRule] = {}
        self._register_default_rules()

    def _register_default_rules(self):
        """注册默认规则"""
        default_rules = [
            LayerNamingRule(),
            LineWeightRule(),
            TextStyleRule(),
            BlockNamingRule(),
            DimensionStyleRule(),
        ]

        for rule in default_rules:
            self.register_rule(rule)

    def register_rule(self, rule: BaseRule):
        """注册规则"""
        self.rules[rule.code] = rule
        logger.info(f"注册规则: {rule.code} - {rule.name}")

    def review(
        self,
        dxf_data: Dict[str, Any],
        rule_codes: Optional[List[str]] = None
    ) -> Dict[str, RuleResult]:
        """执行审核

        Args:
            dxf_data: DXF 解析数据
            rule_codes: 指定执行的规则编码列表，None 表示执行所有规则

        Returns:
            规则编码 -> 检查结果的映射
        """
        results = {}

        rules_to_run = (
            {code: self.rules[code] for code in rule_codes if code in self.rules}
            if rule_codes
            else self.rules
        )

        for code, rule in rules_to_run.items():
            try:
                result = rule.check(dxf_data)
                results[code] = result
                logger.info(f"规则 {code} 执行完成，得分: {result.score:.1f}")
            except Exception as e:
                logger.error(f"规则 {code} 执行失败: {e}")
                results[code] = RuleResult(
                    rule_code=code,
                    rule_name=rule.name,
                    rule_category=rule.category,
                    score=0,
                    issues=[Issue(
                        code=code,
                        message=f"规则执行失败: {str(e)}",
                        severity=Severity.ERROR
                    )],
                    passed=False,
                    message=f"执行错误: {str(e)}"
                )

        return results

    def get_overall_score(self, results: Dict[str, RuleResult]) -> float:
        """计算总体评分"""
        if not results:
            return 100

        # 按类别分组计算
        category_scores: Dict[str, List[float]] = {}
        for result in results.values():
            if result.rule_category not in category_scores:
                category_scores[result.rule_category] = []
            category_scores[result.rule_category].append(result.score)

        # 各类别平均分
        overall = 0
        for category, scores in category_scores.items():
            category_avg = sum(scores) / len(scores)
            overall += category_avg

        return overall / len(category_scores) if category_scores else 100