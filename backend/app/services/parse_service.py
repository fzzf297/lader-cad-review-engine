"""
解析服务 - 处理合同和图纸的解析详情查询
"""
from typing import Dict, List, Any, Optional
import logging
import re
import math
from pathlib import Path
from datetime import datetime

from ..parsers.dxf_parser import DxfParser, DxfParseResult
from ..parsers.contract_parser import ContractParser, ContractContent, WorkItemExtractor
from ..services.review_service import ContractAnalysisService, ContractAnalysisResult, WorkItem
from ..services.legend_counter import LegendCounter
from ..core.config import settings

logger = logging.getLogger(__name__)


# 缓存解析结果
_dxf_parse_cache: Dict[str, DxfParseResult] = {}
_contract_parse_cache: Dict[str, ContractContent] = {}
_contract_analysis_cache: Dict[str, ContractAnalysisResult] = {}


class ParseService:
    """解析服务"""

    def __init__(self):
        self.dxf_parser = DxfParser()
        self.contract_parser = ContractParser()
        self.contract_analyzer = None

        if settings.LLM_ENABLED and settings.QWEN_API_KEY:
            self.contract_analyzer = ContractAnalysisService(
                api_key=settings.QWEN_API_KEY,
                model=settings.QWEN_MODEL,
                base_url=settings.QWEN_BASE_URL,
            )
        self.legend_counter = LegendCounter()

    async def parse_dxf(self, file_path: str, file_id: str) -> DxfParseResult:
        """解析 DXF 文件（带缓存）"""
        if file_id in _dxf_parse_cache:
            return _dxf_parse_cache[file_id]

        result = self.dxf_parser.parse(file_path)
        _dxf_parse_cache[file_id] = result
        return result

    async def count_legend(
        self,
        file_path: str,
        file_id: str,
        query: str,
        use_llm: bool = False,
        save_template: bool = False,
        template_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        dxf_result = await self.parse_dxf(file_path, file_id)
        result = await self.legend_counter.count(
            dxf_result=dxf_result,
            query=query,
            use_llm=use_llm,
            save_template=save_template,
            template_name=template_name,
        )
        return result.__dict__

    async def discover_legends(
        self,
        file_path: str,
        file_id: str,
    ) -> Dict[str, Any]:
        dxf_result = await self.parse_dxf(file_path, file_id)
        items = await self.legend_counter.discover(dxf_result)
        return {
            "file_id": file_id,
            "total_items": len(items),
            "items": items,
        }

    async def get_dwg_preview(
        self,
        file_path: str,
        file_id: str,
    ) -> Dict[str, Any]:
        dxf_result = await self.parse_dxf(file_path, file_id)
        entities: List[Dict[str, Any]] = []
        points: List[tuple[float, float]] = []
        max_entities = 4000
        max_insert_expansions = 220

        def add_point(point: Optional[Dict[str, Any]]) -> None:
            if not point:
                return
            points.append((float(point.get("x", 0.0)), float(point.get("y", 0.0))))

        for entity in dxf_result.entities:
            if len(entities) >= max_entities:
                break
            entity_type = entity.get("type")
            if entity_type == "LINE":
                add_point(entity.get("start"))
                add_point(entity.get("end"))
                entities.append({
                    "type": "LINE",
                    "start": entity.get("start"),
                    "end": entity.get("end"),
                })
            elif entity_type in {"LWPOLYLINE", "POLYLINE"}:
                vertices = entity.get("vertices", [])
                if len(vertices) < 2:
                    continue
                for vertex in vertices:
                    add_point(vertex)
                entities.append({
                    "type": "POLYLINE",
                    "vertices": vertices,
                    "closed": bool(entity.get("closed", False)),
                })
            elif entity_type == "CIRCLE":
                center = entity.get("center")
                radius = float(entity.get("radius", 0.0) or 0.0)
                if not center or radius <= 0:
                    continue
                add_point({"x": float(center.get("x", 0.0)) - radius, "y": float(center.get("y", 0.0)) - radius})
                add_point({"x": float(center.get("x", 0.0)) + radius, "y": float(center.get("y", 0.0)) + radius})
                entities.append({
                    "type": "CIRCLE",
                    "center": center,
                    "radius": radius,
                })
            elif entity_type == "ARC":
                center = entity.get("center")
                radius = float(entity.get("radius", 0.0) or 0.0)
                if not center or radius <= 0:
                    continue
                add_point({"x": float(center.get("x", 0.0)) - radius, "y": float(center.get("y", 0.0)) - radius})
                add_point({"x": float(center.get("x", 0.0)) + radius, "y": float(center.get("y", 0.0)) + radius})
                entities.append({
                    "type": "ARC",
                    "center": center,
                    "radius": radius,
                    "start_angle": float(entity.get("start_angle", 0.0) or 0.0),
                    "end_angle": float(entity.get("end_angle", 0.0) or 0.0),
                })
            elif entity_type in {"TEXT", "MTEXT"}:
                insert = entity.get("insert")
                content = self._normalize_preview_text(entity.get("content", ""))
                if not insert or not content:
                    continue
                add_point(insert)
                entities.append({
                    "type": "TEXT",
                    "insert": insert,
                    "content": content,
                    "height": float(entity.get("height", 0.0) or 0.0),
                    "rotation": float(entity.get("rotation", 0.0) or 0.0),
                })

        expansion_count = 0
        for insert in dxf_result.inserts:
            if len(entities) >= max_entities or expansion_count >= max_insert_expansions:
                break

            block_name = insert.get("name")
            block = dxf_result.blocks.get(block_name or "")
            if not block:
                continue

            block_entities = block.get("entities", [])
            if not block_entities or len(block_entities) > 40:
                continue

            for preview_entity in self._expand_insert_preview(block_entities, insert):
                if len(entities) >= max_entities:
                    break
                entity_type = preview_entity.get("type")
                if entity_type == "LINE":
                    add_point(preview_entity.get("start"))
                    add_point(preview_entity.get("end"))
                elif entity_type == "POLYLINE":
                    for vertex in preview_entity.get("vertices", []):
                        add_point(vertex)
                elif entity_type == "CIRCLE":
                    center = preview_entity.get("center")
                    radius = float(preview_entity.get("radius", 0.0) or 0.0)
                    if center and radius > 0:
                        add_point({"x": float(center.get("x", 0.0)) - radius, "y": float(center.get("y", 0.0)) - radius})
                        add_point({"x": float(center.get("x", 0.0)) + radius, "y": float(center.get("y", 0.0)) + radius})
                elif entity_type == "ARC":
                    center = preview_entity.get("center")
                    radius = float(preview_entity.get("radius", 0.0) or 0.0)
                    if center and radius > 0:
                        add_point({"x": float(center.get("x", 0.0)) - radius, "y": float(center.get("y", 0.0)) - radius})
                        add_point({"x": float(center.get("x", 0.0)) + radius, "y": float(center.get("y", 0.0)) + radius})
                elif entity_type == "TEXT":
                    add_point(preview_entity.get("insert"))

                entities.append(preview_entity)

            expansion_count += 1

        if not points:
            bounds = {"min_x": 0.0, "max_x": 1.0, "min_y": 0.0, "max_y": 1.0}
        else:
            bounds = {
                "min_x": min(point[0] for point in points),
                "max_x": max(point[0] for point in points),
                "min_y": min(point[1] for point in points),
                "max_y": max(point[1] for point in points),
            }

        return {
            "file_id": file_id,
            "bounds": bounds,
            "entities": entities[:max_entities],
        }

    def _normalize_preview_text(self, content: str) -> str:
        normalized = (
            (content or "")
            .replace("\\P", " ")
            .replace("\n", " ")
            .replace("\r", " ")
        )
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized[:24]

    def _transform_insert_point(self, point: Dict[str, Any], insert: Dict[str, Any]) -> Dict[str, float]:
        local_x = float(point.get("x", 0.0))
        local_y = float(point.get("y", 0.0))
        scale = insert.get("scale", {}) or {}
        scale_x = float(scale.get("x", 1.0) or 1.0)
        scale_y = float(scale.get("y", 1.0) or 1.0)
        rotation = math.radians(float(insert.get("rotation", 0.0) or 0.0))
        insert_point = insert.get("insert", {}) or {}

        scaled_x = local_x * scale_x
        scaled_y = local_y * scale_y
        rotated_x = scaled_x * math.cos(rotation) - scaled_y * math.sin(rotation)
        rotated_y = scaled_x * math.sin(rotation) + scaled_y * math.cos(rotation)

        return {
            "x": float(insert_point.get("x", 0.0)) + rotated_x,
            "y": float(insert_point.get("y", 0.0)) + rotated_y,
        }

    def _expand_insert_preview(self, block_entities: List[Dict[str, Any]], insert: Dict[str, Any]) -> List[Dict[str, Any]]:
        preview_entities: List[Dict[str, Any]] = []
        scale = insert.get("scale", {}) or {}
        scale_factor = max(abs(float(scale.get("x", 1.0) or 1.0)), abs(float(scale.get("y", 1.0) or 1.0)))
        insert_rotation = float(insert.get("rotation", 0.0) or 0.0)

        for entity in block_entities:
            entity_type = entity.get("type")
            if entity_type == "LINE":
                preview_entities.append({
                    "type": "LINE",
                    "start": self._transform_insert_point(entity.get("start", {}), insert),
                    "end": self._transform_insert_point(entity.get("end", {}), insert),
                })
            elif entity_type in {"LWPOLYLINE", "POLYLINE"}:
                vertices = [
                    self._transform_insert_point(vertex, insert)
                    for vertex in entity.get("vertices", [])
                ]
                if len(vertices) >= 2:
                    preview_entities.append({
                        "type": "POLYLINE",
                        "vertices": vertices,
                        "closed": bool(entity.get("closed", False)),
                    })
            elif entity_type == "CIRCLE":
                center = entity.get("center")
                radius = float(entity.get("radius", 0.0) or 0.0)
                if center and radius > 0:
                    preview_entities.append({
                        "type": "CIRCLE",
                        "center": self._transform_insert_point(center, insert),
                        "radius": max(radius * scale_factor, 1.0),
                    })
            elif entity_type == "ARC":
                center = entity.get("center")
                radius = float(entity.get("radius", 0.0) or 0.0)
                if center and radius > 0:
                    preview_entities.append({
                        "type": "ARC",
                        "center": self._transform_insert_point(center, insert),
                        "radius": max(radius * scale_factor, 1.0),
                        "start_angle": float(entity.get("start_angle", 0.0) or 0.0) + insert_rotation,
                        "end_angle": float(entity.get("end_angle", 0.0) or 0.0) + insert_rotation,
                    })
            elif entity_type in {"TEXT", "MTEXT"}:
                text_insert = entity.get("insert")
                content = self._normalize_preview_text(entity.get("content", ""))
                if text_insert and content:
                    preview_entities.append({
                        "type": "TEXT",
                        "insert": self._transform_insert_point(text_insert, insert),
                        "content": content,
                        "height": max(float(entity.get("height", 0.0) or 0.0) * scale_factor, 1.0),
                        "rotation": float(entity.get("rotation", 0.0) or 0.0) + insert_rotation,
                    })

        return preview_entities

    def parse_contract(self, file_path: str, file_id: str) -> ContractContent:
        """解析合同文件（带缓存）"""
        if file_id in _contract_parse_cache:
            return _contract_parse_cache[file_id]

        result = self.contract_parser.parse(file_path)
        _contract_parse_cache[file_id] = result
        return result

    async def analyze_contract(self, file_path: str, file_id: str) -> ContractAnalysisResult:
        """分析合同内容（带缓存）"""
        if file_id in _contract_analysis_cache:
            return _contract_analysis_cache[file_id]

        # 先解析合同
        contract_content = self.parse_contract(file_path, file_id)

        # 使用 LLM 分析
        if self.contract_analyzer:
            result = await self.contract_analyzer.analyze(contract_content)
        else:
            # 备用方案：关键词提取
            extractor = WorkItemExtractor()
            work_items_data = extractor.extract_from_text(contract_content.full_text)
            work_items_data.extend(extractor.extract_from_tables(contract_content.tables))

            work_items = [
                WorkItem(
                    name=item["name"],
                    category=item["category"],
                    quantity=item["quantity"],
                    unit=item["unit"],
                    specification=item["specification"]
                )
                for item in work_items_data
            ]
            result = ContractAnalysisResult(work_items=work_items)

        _contract_analysis_cache[file_id] = result
        return result

    def get_dxf_layers(self, dxf_result: DxfParseResult) -> List[Dict[str, Any]]:
        """获取图层列表"""
        layers = []
        for name, info in dxf_result.layers.items():
            layers.append({
                "name": info["name"],
                "color": info["color"],
                "linetype": info["linetype"],
                "off": info.get("off", False),
                "frozen": info.get("frozen", False),
                "locked": info.get("locked", False),
                "plot": info.get("plot", True),
            })
        return layers

    def get_dxf_blocks(self, dxf_result: DxfParseResult) -> List[Dict[str, Any]]:
        """获取图块列表"""
        blocks = []
        for name, info in dxf_result.blocks.items():
            # 获取图块中的实体类型
            entity_types = set()
            for entity in info.get("entities", []):
                entity_types.add(entity.get("type", "UNKNOWN"))

            blocks.append({
                "name": info["name"],
                "entity_count": info["entity_count"],
                "insert_count": info["insert_count"],
                "is_door_window": info.get("is_door_window", False),
                "category": self._categorize_block(info["name"]),
                "entities": list(entity_types),
            })
        return blocks

    def _categorize_block(self, block_name: str) -> str:
        """根据图块名称判断分类"""
        import re
        name_upper = block_name.upper()

        # 门窗
        if any(kw in name_upper for kw in ["门", "窗", "DOOR", "WINDOW", "M", "C"]):
            if re.match(r'^[MC]\d{2,4}$', name_upper):
                return "门窗"
            if any(kw in name_upper for kw in ["门", "DOOR", "M"]):
                return "门窗"
            if any(kw in name_upper for kw in ["窗", "WINDOW", "C"]):
                return "门窗"

        # 管道
        if any(kw in name_upper for kw in ["管", "PIPE", "DUCT", "水", "风"]):
            return "管道"

        # 电气
        if any(kw in name_upper for kw in ["电", "开关", "插座", "灯具", "ELEC"]):
            return "电气"

        # 土建
        if any(kw in name_upper for kw in ["柱", "梁", "板", "墙", "COLUMN", "BEAM", "SLAB"]):
            return "土建"

        # 装修
        if any(kw in name_upper for kw in ["吊顶", "地面", "墙裙", "CEILING", "FLOOR"]):
            return "装修"

        return "其他"

    def get_dxf_entities(
        self,
        dxf_result: DxfParseResult,
        entity_type: Optional[str] = None,
        layer: Optional[str] = None,
        page: int = 1,
        page_size: int = 50
    ) -> Dict[str, Any]:
        """获取实体列表（支持筛选和分页）"""
        entities = dxf_result.entities

        # 筛选
        if entity_type:
            entities = [e for e in entities if e.get("type") == entity_type]
        if layer:
            entities = [e for e in entities if e.get("layer") == layer]

        # 分页
        total = len(entities)
        total_pages = (total + page_size - 1) // page_size if total > 0 else 1
        start = (page - 1) * page_size
        end = start + page_size
        paged_entities = entities[start:end]

        return {
            "entities": paged_entities,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
            }
        }

    def get_dxf_texts(self, dxf_result: DxfParseResult) -> List[Dict[str, Any]]:
        """获取文字内容"""
        texts = []
        for text in dxf_result.texts:
            base_info = {
                "type": text.get("type"),
                "handle": text.get("handle"),
                "layer": text.get("layer"),
                "content": text.get("content", ""),
                "insert": text.get("insert", {}),
                "height": text.get("height", 0),
                "style": text.get("style", ""),
            }
            if text.get("type") == "MTEXT":
                base_info["width"] = text.get("width")
            if text.get("type") == "TEXT":
                base_info["rotation"] = text.get("rotation")
            texts.append(base_info)
        return texts

    def get_dxf_dimensions(self, dxf_result: DxfParseResult) -> List[Dict[str, Any]]:
        """获取尺寸标注"""
        dimensions = []
        for dim in dxf_result.dimensions:
            dimensions.append({
                "handle": dim.get("handle", ""),
                "layer": dim.get("layer", ""),
                "dim_type": dim.get("dim_type", ""),
                "text": dim.get("text", ""),
                "defpoint": dim.get("defpoint", {}),
                "text_position": dim.get("text_position", {}),
                "style": dim.get("style", ""),
            })
        return dimensions

    def get_door_window_stats(self, dxf_result: DxfParseResult) -> Dict[str, Any]:
        """获取门窗统计详情"""
        doors = []
        windows = []

        for name, block in dxf_result.blocks.items():
            if not block.get("is_door_window"):
                continue

            name_upper = name.upper()
            insert_count = block.get("insert_count", 0)

            # 获取插入位置
            locations = []
            for insert in dxf_result.inserts:
                if insert.get("name") == name:
                    locations.append({
                        "x": insert.get("insert", {}).get("x", 0),
                        "y": insert.get("insert", {}).get("y", 0),
                        "z": insert.get("insert", {}).get("z", 0),
                        "layer": insert.get("layer", ""),
                    })

            # 解析规格 (M1021 -> 1000x2100)
            spec = self._parse_specification(name)

            detail = {
                "block_name": name,
                "count": insert_count,
                "specification": spec,
                "locations": locations[:10],  # 最多返回10个位置
            }

            # 分类
            if any(kw in name_upper for kw in ["门", "DOOR", "M"]):
                if re.match(r'^M\d{2,4}$', name_upper):
                    doors.append(detail)
                elif any(kw in name_upper for kw in ["门", "DOOR"]):
                    doors.append(detail)

            if any(kw in name_upper for kw in ["窗", "WINDOW", "C"]):
                if re.match(r'^C\d{2,4}$', name_upper):
                    windows.append(detail)
                elif any(kw in name_upper for kw in ["窗", "WINDOW"]):
                    windows.append(detail)

        total_doors = sum(d["count"] for d in doors)
        total_windows = sum(w["count"] for w in windows)

        return {
            "summary": {
                "total_doors": total_doors,
                "total_windows": total_windows,
                "total_door_window_blocks": len(doors) + len(windows),
            },
            "doors": doors,
            "windows": windows,
        }

    def _parse_specification(self, block_name: str) -> str:
        """从图块名称解析规格"""
        import re
        match = re.match(r'^[MC](\d{2})(\d{2,3})$', block_name.upper())
        if match:
            width = int(match.group(1)) * 10  # cm to mm
            height = int(match.group(2)) * 10 if len(match.group(2)) == 2 else int(match.group(2))
            return f"{width}x{height}"
        return ""

    def get_dxf_statistics(self, dxf_result: DxfParseResult, file_path: str) -> Dict[str, Any]:
        """获取图纸完整统计（包含解析元数据）"""
        # 按类型统计
        by_type = {}
        for entity in dxf_result.entities:
            etype = entity.get("type", "UNKNOWN")
            by_type[etype] = by_type.get(etype, 0) + 1

        # 按分类统计
        by_category = {}
        for block in dxf_result.blocks.values():
            category = self._categorize_block(block["name"])
            if category not in by_category:
                by_category[category] = {"blocks": 0, "inserts": 0}
            by_category[category]["blocks"] += 1
            by_category[category]["inserts"] += block.get("insert_count", 0)

        # 获取文件信息
        file_path_obj = Path(file_path)
        file_size = 0
        if file_path_obj.exists():
            file_size = file_path_obj.stat().st_size

        return {
            "file_info": {
                "dxf_version": dxf_result.file_info.get("dxf_version", ""),
                "units": dxf_result.file_info.get("units", 0),
                "units_name": dxf_result.file_info.get("units_name", ""),
                "filename": dxf_result.file_info.get("filename", file_path_obj.name),
            },
            "counts": {
                "layers": len(dxf_result.layers),
                "blocks": len(dxf_result.blocks),
                "entities": len(dxf_result.entities),
                "dimensions": len(dxf_result.dimensions),
                "texts": len(dxf_result.texts),
                "inserts": len(dxf_result.inserts),
            },
            "by_type": by_type,
            "by_category": by_category,
            "parse_metadata": dxf_result.parse_metadata,
            "source_file": {
                "path": str(file_path),
                "size": file_size,
                "size_formatted": self._format_file_size(file_size),
            }
        }

    def _format_file_size(self, size: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} TB"

    async def get_contract_details(
        self,
        contract_result: ContractAnalysisResult,
        contract_content: ContractContent,
        file_id: str,
        filename: str
    ) -> Dict[str, Any]:
        """获取合同解析详情（完整版）"""
        # 转换工作项
        work_items = [
            {
                "name": item.name,
                "category": item.category,
                "quantity": item.quantity,
                "unit": item.unit,
                "specification": item.specification,
                "location": item.location,
                "deadline": item.deadline,
                "original_text": item.original_text,
            }
            for item in contract_result.work_items
        ]

        # 关键条款
        key_terms = contract_result.key_terms if contract_result.key_terms else []

        # 原文预览（前500字）
        raw_text_preview = contract_content.full_text[:500] if contract_content.full_text else ""

        # 表格预览
        tables_preview = []
        for table in contract_content.tables[:3]:  # 最多3个表格
            if table:
                preview = f"表格: {len(table)}行"
                if table[0]:
                    preview += f", 列: {', '.join(str(c)[:20] for c in table[0][:3])}"
                tables_preview.append(preview)

        return {
            "file_id": file_id,
            "filename": filename,
            "parse_status": "success",
            "parse_result": {
                "project_name": contract_result.project_name,
                "contract_parties": contract_result.contract_parties,
                "total_amount": contract_result.total_amount,
                "work_items": work_items,
                "key_terms": key_terms,
            },
            "raw_text_preview": raw_text_preview,
            "tables_preview": tables_preview,
            "parse_time": datetime.now().isoformat(),
        }

    async def get_construction_scope(
        self,
        file_path: str,
        file_id: str,
        filename: str
    ) -> Dict[str, Any]:
        """获取发包人供应材料设备一览表（专用接口）"""
        # 解析合同
        contract_content = self.parse_contract(file_path, file_id)

        # 使用 LLM 分析材料设备供应表
        if self.contract_analyzer:
            scope_data = await self.contract_analyzer.analyze_material_supply_list(contract_content)
        else:
            scope_data = {"error": "LLM 未启用，无法提取材料设备表"}

        return {
            "file_id": file_id,
            "filename": filename,
            "parse_status": "success" if "error" not in scope_data else "error",
            "material_supply_list": scope_data,
            "parse_time": datetime.now().isoformat(),
        }

    async def get_comparison_details(
        self,
        contract_analysis: ContractAnalysisResult,
        dxf_result: DxfParseResult
    ) -> Dict[str, Any]:
        """获取对比详情"""
        from ..services.review_service import ContractDwgMatcher

        matcher = ContractDwgMatcher()

        # 获取合同-图纸对比结果
        comparison = await matcher.compare(
            contract_analysis.work_items,
            dxf_result.__dict__
        )

        # 转换详情
        details = []
        for match in comparison.match_results:
            # 获取该分类下的所有图块
            dwg_items = []
            dwg_quantity = 0
            for block_name, block in dxf_result.blocks.items():
                block_category = self._categorize_block(block_name)
                if block_category == match.contract_item.category:
                    dwg_items.append({
                        "name": block_name,
                        "count": block.get("insert_count", 0)
                    })
                    dwg_quantity += block.get("insert_count", 0)

            # 获取位置信息
            locations = []
            for insert in dxf_result.inserts:
                for item in dwg_items:
                    if insert.get("name") == item["name"]:
                        locations.append({
                            "x": insert.get("insert", {}).get("x", 0),
                            "y": insert.get("insert", {}).get("y", 0),
                        })
                        break

            details.append({
                "contract_item": {
                    "name": match.contract_item.name,
                    "category": match.contract_item.category,
                    "quantity": match.contract_item.quantity,
                    "unit": match.contract_item.unit,
                },
                "dwg_data": {
                    "block_name": match.contract_item.category,
                    "count": dwg_quantity,
                    "locations": locations[:5],
                },
                "status": match.match_status,
                "difference": match.difference,
                "difference_percent": match.difference_percent,
                "notes": match.notes,
            })

        return {
            "overall_compliance": comparison.overall_compliance,
            "summary": {
                "total_contract_items": comparison.total_contract_items,
                "matched": comparison.matched_items,
                "partial": comparison.partial_match_items,
                "missing": comparison.missing_items,
                "extra": comparison.extra_dwg_items,
            },
            "details": details,
            "issues": comparison.issues,
        }
