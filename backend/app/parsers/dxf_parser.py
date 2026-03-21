"""
DXF 解析器 - 负责解析 DXF 文件并提取结构化数据
"""
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
import ezdxf
from ezdxf.document import Drawing
from ezdxf.entities import DXFEntity
import logging
import math
import hashlib
import time
from pathlib import Path
from datetime import datetime
import tempfile

logger = logging.getLogger(__name__)


@dataclass
class DxfParseResult:
    """DXF 解析结果"""
    file_info: Dict[str, Any] = field(default_factory=dict)
    layers: Dict[str, Dict] = field(default_factory=dict)
    blocks: Dict[str, Dict] = field(default_factory=dict)
    entities: List[Dict] = field(default_factory=list)
    dimensions: List[Dict] = field(default_factory=list)
    texts: List[Dict] = field(default_factory=list)
    inserts: List[Dict] = field(default_factory=list)
    statistics: Dict[str, int] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    parse_metadata: Dict[str, Any] = field(default_factory=dict)  # 解析元数据
    block_signatures: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    raw_texts: List[Dict] = field(default_factory=list)


class EntityExtractor:
    """DXF 实体提取器"""

    def extract(self, entity: DXFEntity) -> Optional[Dict[str, Any]]:
        """根据实体类型提取数据"""
        extractor_map = {
            "LINE": self._extract_line,
            "ARC": self._extract_arc,
            "CIRCLE": self._extract_circle,
            "LWPOLYLINE": self._extract_lwpolyline,
            "POLYLINE": self._extract_polyline,
            "TEXT": self._extract_text,
            "MTEXT": self._extract_mtext,
            "DIMENSION": self._extract_dimension,
            "INSERT": self._extract_insert,
            "POINT": self._extract_point,
            "ELLIPSE": self._extract_ellipse,
            "SPLINE": self._extract_spline,
        }

        entity_type = entity.dxftype()
        extractor = extractor_map.get(entity_type)

        if extractor:
            result = extractor(entity)
            result["type"] = entity_type
            result["layer"] = entity.dxf.layer
            result["handle"] = entity.dxf.handle
            return result

        return None

    def _extract_line(self, entity) -> Dict:
        """提取直线"""
        start = entity.dxf.start
        end = entity.dxf.end
        dx = end.x - start.x
        dy = end.y - start.y
        dz = end.z - start.z
        length = math.sqrt(dx*dx + dy*dy + dz*dz)

        return {
            "start": {"x": start.x, "y": start.y, "z": start.z},
            "end": {"x": end.x, "y": end.y, "z": end.z},
            "length": length,
            "linetype": entity.dxf.linetype,
            "color": entity.dxf.color,
        }

    def _extract_arc(self, entity) -> Dict:
        """提取圆弧"""
        center = entity.dxf.center
        radius = entity.dxf.radius
        angle = math.radians(entity.dxf.end_angle - entity.dxf.start_angle)
        arc_length = radius * abs(angle)

        return {
            "center": {"x": center.x, "y": center.y, "z": center.z},
            "radius": radius,
            "start_angle": entity.dxf.start_angle,
            "end_angle": entity.dxf.end_angle,
            "arc_length": arc_length,
        }

    def _extract_circle(self, entity) -> Dict:
        """提取圆"""
        center = entity.dxf.center
        radius = entity.dxf.radius

        return {
            "center": {"x": center.x, "y": center.y, "z": center.z},
            "radius": radius,
            "area": math.pi * radius ** 2,
            "circumference": 2 * math.pi * radius,
        }

    def _extract_lwpolyline(self, entity) -> Dict:
        """提取轻量多段线"""
        vertices = []
        for point in entity:
            vertices.append({"x": point[0], "y": point[1]})

        length = self._calculate_polyline_length(vertices, entity.closed)

        return {
            "vertices": vertices,
            "vertex_count": len(vertices),
            "closed": entity.closed,
            "length": length,
        }

    def _extract_polyline(self, entity) -> Dict:
        """提取多段线"""
        vertices = []
        for vertex in entity.vertices:
            loc = vertex.dxf.location
            vertices.append({"x": loc.x, "y": loc.y, "z": loc.z})

        return {
            "vertices": vertices,
            "vertex_count": len(vertices),
            "closed": entity.is_closed,
        }

    def _calculate_polyline_length(self, vertices: list, closed: bool) -> float:
        """计算多段线长度"""
        if len(vertices) < 2:
            return 0

        length = 0
        for i in range(len(vertices) - 1):
            dx = vertices[i+1]["x"] - vertices[i]["x"]
            dy = vertices[i+1]["y"] - vertices[i]["y"]
            length += math.sqrt(dx*dx + dy*dy)

        if closed and len(vertices) > 2:
            dx = vertices[0]["x"] - vertices[-1]["x"]
            dy = vertices[0]["y"] - vertices[-1]["y"]
            length += math.sqrt(dx*dx + dy*dy)

        return length

    def _extract_text(self, entity) -> Dict:
        """提取单行文字"""
        insert = entity.dxf.insert
        return {
            "content": entity.dxf.text,
            "insert": {"x": insert.x, "y": insert.y, "z": insert.z},
            "height": entity.dxf.height,
            "rotation": entity.dxf.rotation,
            "style": entity.dxf.style,
        }

    def _extract_mtext(self, entity) -> Dict:
        """提取多行文字"""
        insert = entity.dxf.insert
        return {
            "content": entity.text,
            "insert": {"x": insert.x, "y": insert.y, "z": insert.z},
            "height": entity.dxf.char_height,
            "width": entity.dxf.width,
            "attachment_point": entity.dxf.attachment_point,
            "style": entity.dxf.style,
        }

    def _extract_dimension(self, entity) -> Dict:
        """提取尺寸标注"""
        defpoint = entity.dxf.defpoint
        text_midpoint = getattr(entity.dxf, 'text_midpoint', None)

        return {
            "dim_type": entity.dimtype,
            "defpoint": {"x": defpoint.x, "y": defpoint.y, "z": defpoint.z},
            "text": entity.dxf.text,
            "text_position": {
                "x": text_midpoint.x if text_midpoint else 0,
                "y": text_midpoint.y if text_midpoint else 0,
                "z": 0
            },
            "style": entity.dxf.dimstyle,
        }

    def _extract_insert(self, entity) -> Dict:
        """提取图块引用"""
        insert = entity.dxf.insert

        # 提取属性
        attribs = {}
        for attrib in entity.attribs:
            attribs[attrib.dxf.tag] = attrib.dxf.text

        return {
            "name": entity.dxf.name,
            "insert": {"x": insert.x, "y": insert.y, "z": insert.z},
            "scale": {
                "x": entity.dxf.xscale,
                "y": entity.dxf.yscale,
                "z": entity.dxf.zscale,
            },
            "rotation": entity.dxf.rotation,
            "attribs": attribs,
        }

    def _extract_point(self, entity) -> Dict:
        """提取点"""
        loc = entity.dxf.location
        return {
            "location": {"x": loc.x, "y": loc.y, "z": loc.z},
        }

    def _extract_ellipse(self, entity) -> Dict:
        """提取椭圆"""
        center = entity.dxf.center
        major = entity.dxf.major_axis

        return {
            "center": {"x": center.x, "y": center.y, "z": center.z},
            "major_axis": {"x": major.x, "y": major.y, "z": major.z},
            "ratio": entity.dxf.ratio,
            "start_param": entity.dxf.start_param,
            "end_param": entity.dxf.end_param,
        }

    def _extract_spline(self, entity) -> Dict:
        """提取样条曲线"""
        control_points = []
        for point in entity.control_points:
            if hasattr(point, "x"):
                x, y, z = point.x, point.y, point.z
            else:
                x = point[0] if len(point) > 0 else 0.0
                y = point[1] if len(point) > 1 else 0.0
                z = point[2] if len(point) > 2 else 0.0
            control_points.append({"x": float(x), "y": float(y), "z": float(z)})

        return {
            "control_points": control_points,
            "degree": entity.dxf.degree,
            "closed": entity.closed,
        }


class DxfParser:
    """DXF 文件解析器"""

    # 门窗关键词
    DOOR_WINDOW_KEYWORDS = ["门", "窗", "DOOR", "WINDOW", "M", "C", "MC"]

    def __init__(self):
        self.entity_extractor = EntityExtractor()

    def parse(self, file_path: str) -> DxfParseResult:
        """解析 DXF 文件（带详细日志）"""
        start_time = time.time()
        file_path_obj = Path(file_path)
        source_file_path = str(file_path_obj)

        logger.info(f"[DXF解析] 开始解析文件: {file_path}")

        # 计算文件 MD5
        file_md5 = ""
        file_size = 0
        try:
            file_size = file_path_obj.stat().st_size
            with open(file_path, 'rb') as f:
                file_md5 = hashlib.md5(f.read()).hexdigest()
            logger.info(f"[DXF解析] 文件大小: {file_size} bytes, MD5: {file_md5}")
        except Exception as e:
            logger.warning(f"[DXF解析] 计算文件 MD5 失败: {e}")

        cleaned_fallback_used = False
        cleaned_file_path: Optional[str] = None
        try:
            doc = ezdxf.readfile(file_path)
            logger.info(f"[DXF解析] 文件读取成功: {file_path}")
        except IOError as e:
            logger.error(f"[DXF解析] 无法读取文件: {file_path}, 错误: {e}")
            raise
        except ezdxf.DXFStructureError as e:
            logger.warning(f"[DXF解析] DXF 文件结构错误，尝试清洗回退: {file_path}, 错误: {e}")
            cleaned_file_path = self._create_cleaned_copy(file_path)
            if cleaned_file_path is None:
                logger.error(f"[DXF解析] DXF 文件结构错误: {file_path}, 错误: {e}")
                raise
            doc = ezdxf.readfile(cleaned_file_path)
            cleaned_fallback_used = True
            logger.info(f"[DXF解析] 清洗回退读取成功: {cleaned_file_path}")

        result = DxfParseResult(
            file_info=self._extract_file_info(doc),
            layers=self._extract_layers(doc),
            blocks=self._extract_blocks(doc),
        )

        logger.info(f"[DXF解析] 图层数量: {len(result.layers)}, 图块数量: {len(result.blocks)}")

        # 提取模型空间中的实体
        msp = doc.modelspace()
        logger.info(f"[DXF解析] 开始提取模型空间实体...")

        entity_count_by_type = {}
        for entity in msp:
            entity_data = self._extract_entity(entity)
            if entity_data:
                result.entities.append(entity_data)

                # 分类存储
                entity_type = entity_data.get("type")
                entity_count_by_type[entity_type] = entity_count_by_type.get(entity_type, 0) + 1

                if entity_type == "DIMENSION":
                    result.dimensions.append(entity_data)
                elif entity_type in ["TEXT", "MTEXT"]:
                    result.texts.append(entity_data)
                elif entity_type == "INSERT":
                    result.inserts.append(entity_data)

        logger.info(f"[DXF解析] 实体统计: {entity_count_by_type}")

        result.raw_texts = self._extract_raw_texts(source_file_path)
        result.texts = self._merge_texts(result.texts, result.raw_texts)

        # 统计信息
        result.statistics = self._calculate_statistics(result)
        result.block_signatures = self._build_block_signatures(result.blocks)

        # 清洗真实 DXF 中残留的代理字符，避免后续 JSON 序列化失败
        result.file_info = self._sanitize_value(result.file_info)
        result.layers = self._sanitize_value(result.layers)
        result.blocks = self._sanitize_value(result.blocks)
        result.entities = self._sanitize_value(result.entities)
        result.dimensions = self._sanitize_value(result.dimensions)
        result.texts = self._sanitize_value(result.texts)
        result.inserts = self._sanitize_value(result.inserts)
        result.statistics = self._sanitize_value(result.statistics)
        result.block_signatures = self._sanitize_value(result.block_signatures)
        result.raw_texts = self._sanitize_value(result.raw_texts)

        # 记录门窗识别结果
        door_window_blocks = [name for name, block in result.blocks.items() if block.get("is_door_window")]
        logger.info(f"[DXF解析] 识别到门窗图块: {door_window_blocks}")

        # 计算解析耗时
        parse_duration = time.time() - start_time

        # 记录解析元数据
        result.parse_metadata = {
            "parsed_at": datetime.now().isoformat(),
            "parse_duration_seconds": round(parse_duration, 3),
            "file_path": str(file_path),
            "source_file_path": source_file_path,
            "file_size": file_size,
            "file_md5": file_md5,
            "parser_version": "1.1.0",
            "cleaned_fallback_used": cleaned_fallback_used,
            "cleaned_file_path": cleaned_file_path,
            "raw_text_count": len(result.raw_texts),
        }
        result.parse_metadata = self._sanitize_value(result.parse_metadata)

        logger.info(f"[DXF解析] 解析完成，耗时: {parse_duration:.3f}s, "
                   f"实体总数: {len(result.entities)}, "
                   f"门窗数量: {result.statistics.get('door_count', 0)}门/{result.statistics.get('window_count', 0)}窗")

        return result

    def _create_cleaned_copy(self, file_path: str) -> Optional[str]:
        """创建跳过非法组码的临时 DXF 清洗副本。"""
        try:
            raw_lines = Path(file_path).read_text(encoding="utf-8", errors="ignore").splitlines(True)
        except Exception as exc:
            logger.warning(f"[DXF解析] 读取原始 DXF 以清洗失败: {exc}")
            return None

        cleaned_lines: List[str] = []
        removed_lines = 0
        index = 0
        while index < len(raw_lines):
            code_line = raw_lines[index].strip()
            try:
                int(code_line)
                cleaned_lines.append(raw_lines[index])
                if index + 1 < len(raw_lines):
                    cleaned_lines.append(raw_lines[index + 1])
                index += 2
            except ValueError:
                removed_lines += 1
                index += 1

        if not cleaned_lines:
            return None

        tmp = tempfile.NamedTemporaryFile("w", suffix=".dxf", delete=False, encoding="utf-8")
        tmp.writelines(cleaned_lines)
        tmp.close()
        logger.info(f"[DXF解析] 清洗回退生成临时文件: {tmp.name}, 删除非法行数: {removed_lines}")
        return tmp.name

    def _extract_raw_texts(self, file_path: str) -> List[Dict[str, Any]]:
        """从原始 DXF 文本中按 GB18030 兜底提取文字实体。"""
        try:
            raw_lines = Path(file_path).read_text(encoding="gb18030", errors="ignore").splitlines()
        except Exception as exc:
            logger.warning(f"[DXF解析] 原始文字兜底提取失败: {exc}")
            return []

        section_name = ""
        entity_type: Optional[str] = None
        entity_data: Optional[Dict[str, Any]] = None
        texts: List[Dict[str, Any]] = []

        def finalize(current: Optional[Dict[str, Any]], current_type: Optional[str]) -> None:
            if current_type not in {"TEXT", "MTEXT"} or not current:
                return
            content = "".join(current.get("_content_parts", [])).strip()
            if not content:
                return
            texts.append({
                "type": current_type,
                "handle": current.get("handle", ""),
                "layer": current.get("layer", ""),
                "content": content,
                "insert": {
                    "x": current.get("x", 0.0),
                    "y": current.get("y", 0.0),
                    "z": current.get("z", 0.0),
                },
                "height": current.get("height", 0.0),
                "style": current.get("style", ""),
                "rotation": current.get("rotation", 0.0),
                "source": "raw_gbk",
            })

        index = 0
        while index + 1 < len(raw_lines):
            code = raw_lines[index].strip()
            value = raw_lines[index + 1].rstrip("\r\n")
            index += 2

            try:
                group_code = int(code)
            except ValueError:
                continue

            if group_code == 0 and value == "SECTION":
                entity_type = None
                entity_data = None
                continue

            if group_code == 2 and section_name != "ENTITIES":
                section_name = value
                continue

            if group_code == 0 and value == "ENDSEC":
                finalize(entity_data, entity_type)
                entity_type = None
                entity_data = None
                section_name = ""
                continue

            if section_name != "ENTITIES":
                continue

            if group_code == 0:
                finalize(entity_data, entity_type)
                entity_type = value
                entity_data = {
                    "_content_parts": [],
                    "x": 0.0,
                    "y": 0.0,
                    "z": 0.0,
                    "height": 0.0,
                    "rotation": 0.0,
                    "layer": "",
                    "style": "",
                    "handle": "",
                }
                continue

            if entity_type not in {"TEXT", "MTEXT"} or entity_data is None:
                continue

            if group_code in {1, 3}:
                entity_data["_content_parts"].append(value)
            elif group_code == 5:
                entity_data["handle"] = value
            elif group_code == 8:
                entity_data["layer"] = value
            elif group_code == 10:
                entity_data["x"] = self._safe_float(value)
            elif group_code == 20:
                entity_data["y"] = self._safe_float(value)
            elif group_code == 30:
                entity_data["z"] = self._safe_float(value)
            elif group_code == 40:
                entity_data["height"] = self._safe_float(value)
            elif group_code == 50:
                entity_data["rotation"] = self._safe_float(value)
            elif group_code == 7:
                entity_data["style"] = value

        finalize(entity_data, entity_type)
        return texts

    def _sanitize_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return value.encode("utf-8", errors="ignore").decode("utf-8")
        if isinstance(value, list):
            return [self._sanitize_value(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self._sanitize_value(item) for item in value)
        if isinstance(value, dict):
            return {
                self._sanitize_value(key): self._sanitize_value(item)
                for key, item in value.items()
            }
        return value

    def _merge_texts(self, parsed_texts: List[Dict[str, Any]], raw_texts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """合并 ezdxf 与原始兜底文字，优先保留内容更完整的一份。"""
        merged: Dict[Tuple[str, int, int, str], Dict[str, Any]] = {}
        for text in [*parsed_texts, *raw_texts]:
            point = text.get("insert", {})
            key = (
                text.get("type", ""),
                round(float(point.get("x", 0.0)), 3),
                round(float(point.get("y", 0.0)), 3),
                text.get("handle", ""),
            )
            existing = merged.get(key)
            if existing is None or len((text.get("content") or "").strip()) > len((existing.get("content") or "").strip()):
                merged[key] = text
        return list(merged.values())

    def _safe_float(self, value: str) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _extract_file_info(self, doc: Drawing) -> Dict[str, Any]:
        """提取文件基本信息"""
        unit_names = {
            0: "无单位", 1: "英寸", 2: "英尺", 3: "英里",
            4: "毫米", 5: "厘米", 6: "米", 7: "千米",
        }

        return {
            "dxf_version": doc.dxfversion,
            "units": doc.units,
            "units_name": unit_names.get(doc.units, f"未知({doc.units})"),
            "filename": doc.filename,
            "header_vars": {
                "ACADVER": doc.header.get("$ACADVER", "Unknown"),
                "INSUNITS": doc.header.get("$INSUNITS", 0),
                "MEASUREMENT": doc.header.get("$MEASUREMENT", 0),
            }
        }

    def _extract_layers(self, doc: Drawing) -> Dict[str, Dict]:
        """提取图层信息"""
        layers = {}
        for layer in doc.layers:
            layers[layer.dxf.name] = {
                "name": layer.dxf.name,
                "color": layer.dxf.color,
                "linetype": layer.dxf.linetype,
                "off": layer.is_off(),
                "frozen": layer.is_frozen(),
                "locked": layer.is_locked(),
                "plot": layer.dxf.plot,
            }
        return layers

    def _extract_blocks(self, doc: Drawing) -> Dict[str, Dict]:
        """提取图块定义"""
        blocks = {}
        for block in doc.blocks:
            # 跳过匿名块
            if block.name.startswith("*"):
                continue

            block_entities = []
            for entity in block:
                entity_data = self._extract_entity(entity)
                if entity_data:
                    block_entities.append(entity_data)

            # 判断是否为门窗图块
            is_door_window = self._is_door_window_block(block.name)

            blocks[block.name] = {
                "name": block.name,
                "entities": block_entities,
                "entity_count": len(block_entities),
                "insert_count": self._count_inserts(doc, block.name),
                "is_door_window": is_door_window,
            }
        return blocks

    def _is_door_window_block(self, name: str) -> bool:
        """判断是否为门窗图块"""
        name_upper = name.upper()

        # 检查多字符关键词
        multi_char_keywords = ["门", "窗", "DOOR", "WINDOW"]
        if any(kw in name_upper for kw in multi_char_keywords):
            return True

        # 检查单字符关键词（M/C）- 需要更精确匹配
        # M1021, C1515 等标准门窗命名格式
        import re
        if re.match(r'^[MC]\d{2,4}$', name_upper):
            return True

        return False

    def _count_inserts(self, doc: Drawing, block_name: str) -> int:
        """统计图块引用次数"""
        count = 0
        msp = doc.modelspace()
        for entity in msp.query(f'INSERT[name=="{block_name}"]'):
            count += 1
        return count

    def _extract_entity(self, entity: DXFEntity) -> Optional[Dict]:
        """提取实体数据"""
        try:
            return self.entity_extractor.extract(entity)
        except Exception as e:
            logger.warning(f"提取实体失败: {entity.dxftype()}, 错误: {e}")
            return None

    def _calculate_statistics(self, result: DxfParseResult) -> Dict[str, int]:
        """计算统计信息"""
        stats = {
            "layer_count": len(result.layers),
            "block_count": len(result.blocks),
            "entity_count": len(result.entities),
            "dimension_count": len(result.dimensions),
            "text_count": len(result.texts),
            "insert_count": len(result.inserts),
        }

        # 按实体类型统计
        entity_types = {}
        for entity in result.entities:
            etype = entity.get("type", "UNKNOWN")
            entity_types[etype] = entity_types.get(etype, 0) + 1
        stats["by_type"] = entity_types

        # 统计门窗
        door_count = 0
        window_count = 0
        for name, block in result.blocks.items():
            if block.get("is_door_window"):
                name_upper = name.upper()
                insert_count = block.get("insert_count", 0)
                if any(kw in name_upper for kw in ["门", "DOOR", "M"]):
                    door_count += insert_count
                if any(kw in name_upper for kw in ["窗", "WINDOW", "C"]):
                    window_count += insert_count

        stats["door_count"] = door_count
        stats["window_count"] = window_count

        return stats

    def _build_block_signatures(self, blocks: Dict[str, Dict]) -> Dict[str, Dict[str, Any]]:
        """构建图块签名，用于跨块名变体匹配。"""
        signatures: Dict[str, Dict[str, Any]] = {}
        for name, block in blocks.items():
            entity_types = sorted(
                entity.get("type", "UNKNOWN")
                for entity in block.get("entities", [])
            )
            signature = {
                "entity_types": entity_types,
                "entity_type_counts": {
                    entity_type: entity_types.count(entity_type)
                    for entity_type in sorted(set(entity_types))
                },
                "entity_count": block.get("entity_count", 0),
            }
            signatures[name] = signature
        return signatures
