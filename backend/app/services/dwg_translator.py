"""
图纸内容翻译服务 - 将技术性的 CAD 数据转换为业务可懂的施工内容
"""
from typing import Dict, List, Any, Optional
import re
import logging

from ..parsers.dxf_parser import DxfParseResult

logger = logging.getLogger(__name__)


class ConstructionItem:
    """施工项"""
    def __init__(
        self,
        name: str,
        code: str,
        item_type: str,
        count: int,
        size: str = "",
        specification: str = ""
    ):
        self.name = name
        self.code = code
        self.type = item_type
        self.count = count
        self.size = size
        self.specification = specification

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "code": self.code,
            "type": self.type,
            "count": self.count,
            "size": self.size,
            "specification": self.specification,
        }


class DwgContentTranslator:
    """
    图纸内容翻译器

    将 DXF 技术数据转换为业务可理解的施工内容：
    - M1021 -> 铝合金门 1000x2100mm
    - C1515 -> 塑钢窗 1500x1500mm
    """

    # 门类型映射
    DOOR_TYPES = {
        "M": "门",
        "FM": "防火门",
        "GM": "钢门",
        "MM": "木门",
        "LM": "铝合金门",
        "DM": "防盗门",
        "TLM": "推拉门",
        "ZM": "转门",
        "JC": "卷帘门",
    }

    # 窗类型映射
    WINDOW_TYPES = {
        "C": "窗",
        "GC": "钢窗",
        "LC": "铝合金窗",
        "SC": "塑钢窗",
        "TC": "推拉窗",
        "BC": "百叶窗",
        "ZJC": "中悬窗",
        "SJC": "上悬窗",
        "XJC": "下悬窗",
    }

    # 材料关键词
    MATERIAL_KEYWORDS = {
        "铝合金": "铝合金",
        "塑钢": "塑钢",
        "钢": "钢质",
        "木": "木质",
        "防火": "防火",
        "防盗": "防盗",
        "卷帘": "卷帘",
        "百叶": "百叶",
    }

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def translate(self, dxf_result: DxfParseResult) -> Dict[str, Any]:
        """
        将 DXF 解析结果翻译为施工内容

        Returns:
            {
                "doors": [...],
                "windows": [...],
                "rooms": [...],
                "areas": {...},
                "summary": {...}
            }
        """
        logger.info("[图纸翻译] 开始翻译图纸内容...")

        # 提取门
        doors = self._extract_doors(dxf_result)
        logger.info(f"[图纸翻译] 识别到 {len(doors)} 种门，共 {sum(d.count for d in doors)} 个")

        # 提取窗
        windows = self._extract_windows(dxf_result)
        logger.info(f"[图纸翻译] 识别到 {len(windows)} 种窗，共 {sum(w.count for d in windows)} 个")

        # 提取房间信息
        rooms = self._extract_rooms(dxf_result)
        logger.info(f"[图纸翻译] 识别到 {len(rooms)} 个房间")

        # 计算面积（如果有尺寸标注）
        areas = self._calculate_areas(dxf_result)

        # 构建汇总
        summary = {
            "total_doors": sum(d.count for d in doors),
            "total_windows": sum(w.count for w in windows),
            "door_types": len(doors),
            "window_types": len(windows),
            "rooms_count": len(rooms),
        }

        result = {
            "doors": [d.to_dict() for d in doors],
            "windows": [w.to_dict() for w in windows],
            "rooms": rooms,
            "areas": areas,
            "summary": summary,
        }

        logger.info(f"[图纸翻译] 翻译完成: {summary}")
        return result

    def _extract_doors(self, dxf_result: DxfParseResult) -> List[ConstructionItem]:
        """提取门信息"""
        doors = []

        for block_name, block in dxf_result.blocks.items():
            if not block.get("is_door_window"):
                continue

            name_upper = block_name.upper()
            insert_count = block.get("insert_count", 0)

            if insert_count == 0:
                continue

            # 判断是否为门
            is_door = False
            door_prefix = None

            for prefix in ["FM", "GM", "MM", "LM", "DM", "TLM", "ZM", "JC"]:
                if name_upper.startswith(prefix):
                    is_door = True
                    door_prefix = prefix
                    break

            if not is_door and re.match(r'^M\d{2,4}$', name_upper):
                is_door = True
                door_prefix = "M"

            if not is_door:
                continue

            # 解析规格
            spec = self._parse_specification(block_name)

            # 确定门类型和名称
            door_type = self.DOOR_TYPES.get(door_prefix, "门")
            material = self._detect_material(block_name, dxf_result)

            if material:
                full_name = f"{material}{door_type}"
            else:
                full_name = door_type

            # 提取详细规格
            full_spec = self._extract_full_specification(block_name, spec, dxf_result)

            doors.append(ConstructionItem(
                name=full_name,
                code=block_name,
                item_type="door",
                count=insert_count,
                size=spec,
                specification=full_spec
            ))

        # 按数量排序
        doors.sort(key=lambda x: x.count, reverse=True)
        return doors

    def _extract_windows(self, dxf_result: DxfParseResult) -> List[ConstructionItem]:
        """提取窗信息"""
        windows = []

        for block_name, block in dxf_result.blocks.items():
            if not block.get("is_door_window"):
                continue

            name_upper = block_name.upper()
            insert_count = block.get("insert_count", 0)

            if insert_count == 0:
                continue

            # 判断是否为窗
            is_window = False
            window_prefix = None

            for prefix in ["GC", "LC", "SC", "TC", "BC", "ZJC", "SJC", "XJC"]:
                if name_upper.startswith(prefix):
                    is_window = True
                    window_prefix = prefix
                    break

            if not is_window and re.match(r'^C\d{2,4}$', name_upper):
                is_window = True
                window_prefix = "C"

            if not is_window:
                continue

            # 解析规格
            spec = self._parse_specification(block_name)

            # 确定窗类型和名称
            window_type = self.WINDOW_TYPES.get(window_prefix, "窗")
            material = self._detect_material(block_name, dxf_result)

            if material:
                full_name = f"{material}{window_type}"
            else:
                full_name = window_type

            # 提取详细规格
            full_spec = self._extract_full_specification(block_name, spec, dxf_result)

            windows.append(ConstructionItem(
                name=full_name,
                code=block_name,
                item_type="window",
                count=insert_count,
                size=spec,
                specification=full_spec
            ))

        # 按数量排序
        windows.sort(key=lambda x: x.count, reverse=True)
        return windows

    def _parse_specification(self, block_name: str) -> str:
        """从图块名称解析规格 M1021 -> 1000x2100"""
        match = re.match(r'^[MC]|(?:FM|GM|MM|LM|DM|TLM|ZM|JC|GC|LC|SC|TC|BC|ZJC|SJC|XJC)(\d{2})(\d{2,3})$', block_name.upper())
        if match:
            width = int(match.group(1)) * 10  # cm to mm
            height = int(match.group(2)) * 10 if len(match.group(2)) == 2 else int(match.group(2))
            return f"{width}x{height}"
        return ""

    def _detect_material(self, block_name: str, dxf_result: DxfParseResult) -> str:
        """检测材料类型"""
        name_upper = block_name.upper()

        # 从名称判断
        if "铝合金" in name_upper or name_upper.startswith("LM") or name_upper.startswith("LC"):
            return "铝合金"
        if "塑钢" in name_upper or name_upper.startswith("SC"):
            return "塑钢"
        if "钢" in name_upper and (name_upper.startswith("G") or "GM" in name_upper or "GC" in name_upper):
            return "钢质"
        if "防火" in name_upper or name_upper.startswith("FM"):
            return "防火"
        if "木" in name_upper or name_upper.startswith("MM"):
            return "木质"
        if "防盗" in name_upper or name_upper.startswith("DM"):
            return "防盗"

        # 尝试从图块属性或图层判断
        for material_keyword, material_name in self.MATERIAL_KEYWORDS.items():
            if material_keyword in name_upper:
                return material_name

        return ""

    def _extract_full_specification(
        self,
        block_name: str,
        size: str,
        dxf_result: DxfParseResult
    ) -> str:
        """提取完整规格描述"""
        parts = []

        # 添加尺寸
        if size:
            parts.append(f"规格: {size}mm")

        # 尝试从图块实体获取更多信息
        block = dxf_result.blocks.get(block_name, {})
        entities = block.get("entities", [])

        # 统计实体类型
        entity_types = set(e.get("type", "") for e in entities)

        if "LWPOLYLINE" in entity_types:
            parts.append("含多段线轮廓")

        return "; ".join(parts) if parts else ""

    def _extract_rooms(self, dxf_result: DxfParseResult) -> List[Dict[str, Any]]:
        """从文字标注提取房间信息"""
        rooms = []
        room_keywords = [
            "客厅", "卧室", "主卧", "次卧", "客房", "书房",
            "厨房", "餐厅", "卫生间", "浴室", "阳台",
            "玄关", "过道", "走廊", "楼梯", "储藏室",
            "会议室", "办公室", "大厅", "门厅", "前厅"
        ]

        seen_rooms = set()

        for text in dxf_result.texts:
            content = text.get("content", "")
            if not content:
                continue

            # 检查是否包含房间关键词
            for keyword in room_keywords:
                if keyword in content and keyword not in seen_rooms:
                    rooms.append({
                        "name": keyword,
                        "description": content,
                        "area": None  # 暂时无法计算
                    })
                    seen_rooms.add(keyword)
                    break

        return rooms

    def _calculate_areas(self, dxf_result: DxfParseResult) -> Dict[str, float]:
        """从尺寸标注计算面积（简化版）"""
        areas = {}

        # 这里可以实现更复杂的面积计算逻辑
        # 目前仅返回空字典作为占位

        return areas


class DwgParseVerifier:
    """
    DWG 解析验证器

    验证文件是否被真实解析，生成验证报告
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def verify(self, dxf_result: DxfParseResult, file_id: str, filename: str) -> Dict[str, Any]:
        """
        验证解析结果的真实性

        Returns:
            {
                "is_valid": bool,
                "confidence": str,  # high/medium/low
                "checks": [...],
                "indicators": {...}
            }
        """
        checks = []
        indicators = {}

        # 检查 1: 是否有解析元数据
        has_metadata = bool(dxf_result.parse_metadata)
        checks.append({
            "name": "解析元数据",
            "passed": has_metadata,
            "detail": "文件包含解析时间戳和MD5校验" if has_metadata else "缺少解析元数据"
        })

        # 检查 2: 实体数量是否合理
        entity_count = len(dxf_result.entities)
        has_entities = entity_count > 0
        checks.append({
            "name": "实体数量",
            "passed": has_entities,
            "detail": f"发现 {entity_count} 个实体" if has_entities else "未找到任何实体"
        })
        indicators["entity_count"] = entity_count

        # 检查 3: 图层数量是否合理
        layer_count = len(dxf_result.layers)
        has_layers = layer_count > 0
        checks.append({
            "name": "图层信息",
            "passed": has_layers,
            "detail": f"发现 {layer_count} 个图层" if has_layers else "未找到图层信息"
        })
        indicators["layer_count"] = layer_count

        # 检查 4: 是否有门窗图块
        door_window_blocks = [
            name for name, block in dxf_result.blocks.items()
            if block.get("is_door_window") and block.get("insert_count", 0) > 0
        ]
        has_door_windows = len(door_window_blocks) > 0
        checks.append({
            "name": "门窗识别",
            "passed": has_door_windows,
            "detail": f"识别到 {len(door_window_blocks)} 种门窗: {', '.join(door_window_blocks[:5])}" if has_door_windows else "未识别到门窗"
        })
        indicators["door_window_types"] = len(door_window_blocks)
        indicators["door_window_list"] = door_window_blocks[:10]

        # 检查 5: 是否有文字内容
        text_count = len(dxf_result.texts)
        checks.append({
            "name": "文字标注",
            "passed": text_count > 0,
            "detail": f"发现 {text_count} 个文字标注" if text_count > 0 else "未发现文字标注"
        })
        indicators["text_count"] = text_count

        # 计算置信度
        passed_checks = sum(1 for c in checks if c["passed"])
        total_checks = len(checks)

        if passed_checks == total_checks:
            confidence = "high"
        elif passed_checks >= total_checks * 0.6:
            confidence = "medium"
        else:
            confidence = "low"

        # 判断是否有效
        is_valid = has_entities and has_layers

        return {
            "is_valid": is_valid,
            "confidence": confidence,
            "passed_checks": passed_checks,
            "total_checks": total_checks,
            "checks": checks,
            "indicators": indicators,
        }
