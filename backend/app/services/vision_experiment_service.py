"""
多模态可行性实验服务。

当前版本不替换正式统计链路，只提供：
- overview 图
- 图例/内容/排除区域候选
- confirmed / uncertain / excluded 三类点位实验结果
"""
from __future__ import annotations

import asyncio
import base64
import io
import math
from typing import Any, Dict, List, Optional, Tuple

from ..core.config import settings
from ..llm.llm_service import get_vision_candidate_review_service
from ..parsers.dxf_parser import DxfParseResult
from .legend_counter import TITLE_BLOCK_KEYWORDS, LegendCounter

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover
    Image = None
    ImageDraw = None


class VisionExperimentService:
    def __init__(self) -> None:
        self.legend_counter = LegendCounter()
        self.provider = settings.VISION_EXPERIMENT_PROVIDER
        self.model = settings.VISION_EXPERIMENT_MODEL
        self.enabled = settings.VISION_EXPERIMENT_ENABLED
        self.max_model_candidates = max(1, settings.VISION_EXPERIMENT_MAX_MODEL_CANDIDATES)
        self.vision_reviewer = get_vision_candidate_review_service() if self.provider == "qwen" else None

    async def analyze_regions(
        self,
        dxf_result: DxfParseResult,
        preview: Dict[str, Any],
        file_id: str,
    ) -> Dict[str, Any]:
        overview_image = self._render_image_data_uri(
            preview_entities=preview.get("entities", []),
            bounds=preview.get("bounds") or self._empty_bounds(),
        )
        legend_regions = self._build_legend_regions(dxf_result, preview)
        content_regions = self._build_content_regions(dxf_result, preview)
        excluded_regions = self._build_excluded_regions(dxf_result, preview)

        return {
            "file_id": file_id,
            "enabled": self.enabled,
            "provider": self._active_provider_name(),
            "model": self._active_model_name(),
            "overview_image": overview_image,
            "legend_regions": legend_regions,
            "content_regions": content_regions,
            "excluded_regions": excluded_regions,
        }

    async def classify_legend(
        self,
        dxf_result: DxfParseResult,
        preview: Dict[str, Any],
        file_id: str,
        legend_name: str,
    ) -> Dict[str, Any]:
        aliases = [legend_name]
        matched_labels = self.legend_counter._match_label_texts(dxf_result, aliases)
        anchor_labels = self._select_anchor_labels(dxf_result, matched_labels)
        target = self.legend_counter._select_target(dxf_result, anchor_labels, template=None)

        confirmed: List[Dict[str, Any]] = []
        uncertain: List[Dict[str, Any]] = []
        excluded: List[Dict[str, Any]] = []
        strategy = "heuristic-preview"
        explanation = "基于 DXF 预览图与几何候选点做实验性三类分拣。"
        provider_name = self._active_provider_name()
        model_name = self._active_model_name()

        legend_regions = self._build_legend_regions(dxf_result, preview)
        overview_image = self._render_image_data_uri(
            preview_entities=preview.get("entities", []),
            bounds=preview.get("bounds") or self._empty_bounds(),
        )

        if target:
            candidates = self.legend_counter._find_all_matches(dxf_result, target)
            legend_zone_candidates = self.legend_counter._find_legend_zone_candidates(dxf_result, anchor_labels, target)
            legend_zone = self.legend_counter._infer_legend_zone(anchor_labels, legend_zone_candidates)
            cluster_map = self.legend_counter._build_candidate_clusters(candidates)
            generic_block = self.legend_counter._is_generic_library_block(target.get("block_name", ""))

            review_candidates: List[Dict[str, Any]] = []
            for candidate in candidates:
                reasons = self.legend_counter._classify_candidate(
                    candidate=candidate,
                    legend_zone=legend_zone,
                    dxf_result=dxf_result,
                    candidates=candidates,
                    cluster_map=cluster_map,
                    legend_zone_candidates=legend_zone_candidates,
                )
                tile_image = self._build_point_tile(preview, candidate.x, candidate.y)
                base_payload = {
                    "x": candidate.x,
                    "y": candidate.y,
                    "z": candidate.z,
                    "layer": candidate.layer,
                    "block_name": candidate.block_name,
                    "handle": candidate.handle,
                    "image_data": tile_image,
                }

                hard_exclude = any(
                    reason in {
                        "位于图纸边缘样例区",
                        "位于图框标题栏区域",
                        "位于图例候选区域",
                        "位于图例辅助样例区",
                        "位于图例样例簇",
                    }
                    for reason in reasons
                )

                if hard_exclude:
                    excluded.append({
                        **base_payload,
                        "reason": "；".join(reasons),
                        "confidence": 0.9,
                    })
                elif generic_block or reasons:
                    review_candidates.append({
                        **base_payload,
                        "reason": "；".join(reasons) if reasons else "命中的是通用库块，实验链路暂不直接计入。",
                        "confidence": 0.45 if generic_block else 0.58,
                        "heuristic_bucket": "uncertain",
                        "heuristic_reasons": reasons,
                    })
                else:
                    review_candidates.append({
                        **base_payload,
                        "reason": "规则链路未发现排除信号，作为主图候选保留。",
                        "confidence": 0.78,
                        "heuristic_bucket": "confirmed",
                        "heuristic_reasons": reasons,
                    })

            if self.vision_reviewer and review_candidates:
                provider_name = "qwen"
                model_name = self.vision_reviewer.model
                reviewed = await self._apply_qwen_review(
                    review_candidates=review_candidates,
                    dxf_result=dxf_result,
                    legend_name=legend_name,
                    overview_image=overview_image,
                    legend_regions=legend_regions,
                )
                confirmed.extend(reviewed["confirmed"])
                uncertain.extend(reviewed["uncertain"])
                excluded.extend(reviewed["excluded"])
                if reviewed["limited"]:
                    explanation = (
                        f"已调用千问视觉复核 {reviewed['reviewed_count']} 个候选点，"
                        f"其余 {reviewed['remaining_count']} 个候选保持启发式 uncertain。"
                    )
                elif generic_block:
                    explanation = "已调用千问视觉复核通用库块候选，confirmed / uncertain / excluded 为实验性裁决结果。"
                else:
                    explanation = "已调用千问视觉对候选点进行局部图复核，confirmed / uncertain / excluded 为实验性裁决结果。"
            else:
                for item in review_candidates:
                    bucket = item.pop("heuristic_bucket", "uncertain")
                    item.pop("heuristic_reasons", None)
                    if bucket == "confirmed":
                        confirmed.append(item)
                    else:
                        uncertain.append(item)

            if generic_block:
                strategy = "qwen_vision_assisted_generic_block" if self.vision_reviewer else "vision_assisted_generic_block"
                if not self.vision_reviewer:
                    explanation = "目标符号命中的是通用库块，实验链路将其保守降级为 uncertain / excluded，避免输出误导性总数。"
            else:
                strategy = "qwen_vision_assisted_block" if self.vision_reviewer else "vision_assisted_block"
                if not self.vision_reviewer:
                    explanation = "基于图例文字锚点、同类块匹配与区域规则生成实验性三类点位。"
        else:
            strategy = "label_only"
            explanation = "仅识别到图例名称，尚未稳定定位对应符号，实验链路先返回名称级候选。"
            for label in anchor_labels or matched_labels[:6]:
                x, y = self.legend_counter._xy(label.get("insert"))
                uncertain.append({
                    "x": x,
                    "y": y,
                    "z": 0.0,
                    "layer": label.get("layer", ""),
                    "block_name": "",
                    "handle": label.get("handle", ""),
                    "reason": "仅识别到图例名称文字，未稳定找到对应图元。",
                    "confidence": 0.35,
                    "image_data": self._build_point_tile(preview, x, y),
                })

        return {
            "file_id": file_id,
            "legend_name": legend_name,
            "enabled": self.enabled,
            "provider": provider_name,
            "model": model_name,
            "strategy": strategy,
            "overview_image": overview_image,
            "legend_regions": legend_regions,
            "confirmed_matches": confirmed,
            "uncertain_matches": uncertain,
            "excluded_matches": excluded,
            "summary": {
                "confirmed_count": len(confirmed),
                "uncertain_count": len(uncertain),
                "excluded_count": len(excluded),
            },
            "explanation": explanation,
        }

    def _select_anchor_labels(
        self,
        dxf_result: DxfParseResult,
        matched_labels: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        contextual = [item for item in matched_labels if self.legend_counter._has_legend_context(item, dxf_result)]
        if contextual:
            return contextual[:6]

        clusters = self._cluster_texts(matched_labels, distance_threshold=28000.0)
        if not clusters:
            return matched_labels[:6]

        best_cluster = max(
            clusters,
            key=lambda cluster: (
                self._cluster_distinct_device_names(dxf_result, cluster),
                len(cluster),
                -self._cluster_center(cluster)[1],
            ),
        )
        return best_cluster[:6]

    def _build_legend_regions(self, dxf_result: DxfParseResult, preview: Dict[str, Any]) -> List[Dict[str, Any]]:
        labels = self.legend_counter._discover_candidate_labels(dxf_result)
        clusters = self._cluster_texts(labels, distance_threshold=32000.0)
        regions: List[Dict[str, Any]] = []
        for index, cluster in enumerate(
            sorted(
                clusters,
                key=lambda item: (
                    self._cluster_distinct_device_names(dxf_result, item),
                    len(item),
                ),
                reverse=True,
            )[:3]
        ):
            bounds = self._cluster_bounds(cluster, padding=10000.0)
            names = sorted({item.get("normalized_name", "") for item in cluster if item.get("normalized_name")})
            regions.append(self._make_region(
                region_id=f"legend-{index + 1}",
                label=" / ".join(names[:3]) or f"图例候选区 {index + 1}",
                bounds=bounds,
                reason=f"聚集了 {len(names)} 个候选图例名称，共 {len(cluster)} 条相关文字。",
                confidence=min(0.92, 0.45 + len(names) * 0.12 + len(cluster) * 0.03),
                preview=preview,
            ))
        return regions

    def _build_content_regions(self, dxf_result: DxfParseResult, preview: Dict[str, Any]) -> List[Dict[str, Any]]:
        bounds = self.legend_counter._compute_layout_bounds(dxf_result) or self._empty_bounds()
        span_x = max(bounds["max_x"] - bounds["min_x"], 1.0)
        span_y = max(bounds["max_y"] - bounds["min_y"], 1.0)
        content_bounds = {
            "min_x": bounds["min_x"] + span_x * 0.04,
            "max_x": bounds["max_x"] - span_x * 0.04,
            "min_y": bounds["min_y"] + span_y * 0.04,
            "max_y": bounds["max_y"] - span_y * 0.04,
        }
        return [self._make_region(
            region_id="content-main",
            label="主图内容区",
            bounds=content_bounds,
            reason="按整图几何范围扣除边缘留白后得到的主图候选区域。",
            confidence=0.62,
            preview=preview,
        )]

    def _build_excluded_regions(self, dxf_result: DxfParseResult, preview: Dict[str, Any]) -> List[Dict[str, Any]]:
        title_texts = [
            text for text in dxf_result.texts
            if any(keyword in (text.get("content") or "") for keyword in TITLE_BLOCK_KEYWORDS)
        ]
        clusters = self._cluster_texts(title_texts, distance_threshold=22000.0)
        regions: List[Dict[str, Any]] = []
        for index, cluster in enumerate(clusters[:2]):
            regions.append(self._make_region(
                region_id=f"excluded-{index + 1}",
                label="标题栏/说明区",
                bounds=self._cluster_bounds(cluster, padding=8000.0),
                reason="附近存在图框、比例、设计、审核等标题栏关键词。",
                confidence=0.88,
                preview=preview,
            ))
        return regions

    def _cluster_texts(
        self,
        texts: List[Dict[str, Any]],
        distance_threshold: float,
    ) -> List[List[Dict[str, Any]]]:
        if not texts:
            return []

        remaining = texts[:]
        clusters: List[List[Dict[str, Any]]] = []

        while remaining:
            seed = remaining.pop(0)
            cluster = [seed]
            changed = True
            while changed:
                changed = False
                next_remaining: List[Dict[str, Any]] = []
                for candidate in remaining:
                    cx, cy = self.legend_counter._xy(candidate.get("insert"))
                    if any(
                        self.legend_counter._distance((cx, cy), self.legend_counter._xy(item.get("insert"))) <= distance_threshold
                        for item in cluster
                    ):
                        cluster.append(candidate)
                        changed = True
                    else:
                        next_remaining.append(candidate)
                remaining = next_remaining
            clusters.append(cluster)

        return clusters

    def _cluster_distinct_device_names(self, dxf_result: DxfParseResult, cluster: List[Dict[str, Any]]) -> int:
        names = set()
        for item in cluster:
            normalized = item.get("normalized_name") or self.legend_counter._normalize_label_name(item.get("content", ""))
            if normalized and self.legend_counter._looks_like_device_name(normalized):
                names.add(normalized)
        return len(names)

    def _cluster_bounds(self, cluster: List[Dict[str, Any]], padding: float) -> Dict[str, float]:
        xs: List[float] = []
        ys: List[float] = []
        for item in cluster:
            x, y = self.legend_counter._xy(item.get("insert"))
            xs.append(x)
            ys.append(y)
        if not xs or not ys:
            return self._empty_bounds()
        return {
            "min_x": min(xs) - padding,
            "max_x": max(xs) + padding,
            "min_y": min(ys) - padding,
            "max_y": max(ys) + padding,
        }

    def _cluster_center(self, cluster: List[Dict[str, Any]]) -> Tuple[float, float]:
        xs, ys = [], []
        for item in cluster:
            x, y = self.legend_counter._xy(item.get("insert"))
            xs.append(x)
            ys.append(y)
        if not xs:
            return (0.0, 0.0)
        return (sum(xs) / len(xs), sum(ys) / len(ys))

    def _make_region(
        self,
        region_id: str,
        label: str,
        bounds: Dict[str, float],
        reason: str,
        confidence: float,
        preview: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "region_id": region_id,
            "label": label,
            "min_x": bounds["min_x"],
            "max_x": bounds["max_x"],
            "min_y": bounds["min_y"],
            "max_y": bounds["max_y"],
            "confidence": round(max(0.0, min(1.0, confidence)), 2),
            "reason": reason,
            "image_data": self._render_image_data_uri(
                preview_entities=preview.get("entities", []),
                bounds=bounds,
            ),
        }

    def _build_point_tile(self, preview: Dict[str, Any], x: float, y: float) -> str:
        span = 14000.0
        bounds = {
            "min_x": x - span,
            "max_x": x + span,
            "min_y": y - span,
            "max_y": y + span,
        }
        return self._render_image_data_uri(
            preview_entities=preview.get("entities", []),
            bounds=bounds,
            highlighted_points=[{"x": x, "y": y, "color": "#ef4444"}],
            width=320,
            height=220,
        )

    def _render_image_data_uri(
        self,
        preview_entities: List[Dict[str, Any]],
        bounds: Dict[str, float],
        highlighted_points: Optional[List[Dict[str, Any]]] = None,
        width: int = 900,
        height: int = 520,
    ) -> str:
        if Image is None or ImageDraw is None:  # pragma: no cover
            return ""

        min_x = float(bounds.get("min_x", 0.0))
        max_x = float(bounds.get("max_x", min_x + 1.0))
        min_y = float(bounds.get("min_y", 0.0))
        max_y = float(bounds.get("max_y", min_y + 1.0))
        span_x = max(max_x - min_x, 1.0)
        span_y = max(max_y - min_y, 1.0)
        padding = 20
        canvas = Image.new("RGB", (width, height), "#f8fafc")
        draw = ImageDraw.Draw(canvas)

        def scale_x(value: float) -> float:
            return padding + ((value - min_x) / span_x) * (width - padding * 2)

        def scale_y(value: float) -> float:
            return height - padding - ((value - min_y) / span_y) * (height - padding * 2)

        def point_in_bounds(px: float, py: float) -> bool:
            return min_x <= px <= max_x and min_y <= py <= max_y

        draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=12, outline="#cbd5e1", width=1, fill="#f8fafc")

        for entity in preview_entities:
            entity_type = entity.get("type")
            if entity_type == "LINE" and entity.get("start") and entity.get("end"):
                start = entity["start"]
                end = entity["end"]
                if point_in_bounds(start["x"], start["y"]) or point_in_bounds(end["x"], end["y"]):
                    draw.line(
                        (
                            scale_x(start["x"]),
                            scale_y(start["y"]),
                            scale_x(end["x"]),
                            scale_y(end["y"]),
                        ),
                        fill="#94a3b8",
                        width=1,
                    )
            elif entity_type == "POLYLINE" and entity.get("vertices"):
                vertices = entity["vertices"]
                if any(point_in_bounds(vertex["x"], vertex["y"]) for vertex in vertices):
                    scaled = [(scale_x(vertex["x"]), scale_y(vertex["y"])) for vertex in vertices]
                    if entity.get("closed") and scaled:
                        scaled.append(scaled[0])
                    draw.line(scaled, fill="#94a3b8", width=1)
            elif entity_type == "CIRCLE" and entity.get("center") and entity.get("radius"):
                center = entity["center"]
                if point_in_bounds(center["x"], center["y"]):
                    radius = max(1.0, min(
                        (float(entity["radius"]) / span_x) * (width - padding * 2),
                        (float(entity["radius"]) / span_y) * (height - padding * 2),
                    ))
                    cx = scale_x(center["x"])
                    cy = scale_y(center["y"])
                    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline="#94a3b8", width=1)
            elif entity_type == "ARC" and entity.get("center") and entity.get("radius") is not None:
                center = entity["center"]
                if point_in_bounds(center["x"], center["y"]):
                    radius_x = max(1.0, (float(entity["radius"]) / span_x) * (width - padding * 2))
                    radius_y = max(1.0, (float(entity["radius"]) / span_y) * (height - padding * 2))
                    cx = scale_x(center["x"])
                    cy = scale_y(center["y"])
                    start_angle = float(entity.get("start_angle", 0.0) or 0.0)
                    end_angle = float(entity.get("end_angle", 0.0) or 0.0)
                    draw.arc(
                        (cx - radius_x, cy - radius_y, cx + radius_x, cy + radius_y),
                        start=-end_angle,
                        end=-start_angle,
                        fill="#94a3b8",
                        width=1,
                    )
            elif entity_type == "TEXT" and entity.get("insert") and entity.get("content"):
                insert = entity["insert"]
                if point_in_bounds(insert["x"], insert["y"]):
                    content = str(entity.get("content", ""))[:24]
                    draw.text((scale_x(insert["x"]), scale_y(insert["y"])), content, fill="#64748b")

        for point in highlighted_points or []:
            px = scale_x(point["x"])
            py = scale_y(point["y"])
            color = point.get("color", "#ef4444")
            draw.ellipse((px - 5, py - 5, px + 5, py + 5), fill=color, outline="#111827", width=1)

        buffer = io.BytesIO()
        canvas.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    async def _apply_qwen_review(
        self,
        *,
        review_candidates: List[Dict[str, Any]],
        dxf_result: DxfParseResult,
        legend_name: str,
        overview_image: str,
        legend_regions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not self.vision_reviewer:
            return {"confirmed": [], "uncertain": review_candidates, "excluded": [], "limited": False, "reviewed_count": 0, "remaining_count": 0}

        legend_region_image = legend_regions[0]["image_data"] if legend_regions else None
        reviewable = review_candidates[: self.max_model_candidates]
        overflow = review_candidates[self.max_model_candidates :]
        semaphore = asyncio.Semaphore(3)

        async def review_single(candidate: Dict[str, Any]) -> Dict[str, Any]:
            async with semaphore:
                context = {
                    "handle": candidate["handle"],
                    "layer": candidate["layer"],
                    "block_name": candidate["block_name"],
                    "nearby_texts": self._collect_nearby_texts(dxf_result, candidate["x"], candidate["y"]),
                    "heuristic_reason": candidate["reason"],
                }
                result = await self.vision_reviewer.review_candidate(
                    legend_name=legend_name,
                    heuristic_bucket=candidate.get("heuristic_bucket", "uncertain"),
                    overview_image=overview_image,
                    legend_region_image=legend_region_image,
                    candidate_image=candidate["image_data"],
                    context=context,
                )
                reviewed = {key: value for key, value in candidate.items() if key not in {"heuristic_bucket", "heuristic_reasons"}}
                reviewed["reason"] = result["reason"]
                reviewed["confidence"] = result["confidence"] or candidate["confidence"]
                reviewed["classification"] = result["classification"]
                return reviewed

        reviewed_items = await asyncio.gather(*(review_single(item) for item in reviewable))
        confirmed: List[Dict[str, Any]] = []
        uncertain: List[Dict[str, Any]] = []
        excluded: List[Dict[str, Any]] = []

        for item in reviewed_items:
            classification = item.pop("classification", "uncertain")
            if classification == "confirmed":
                confirmed.append(item)
            elif classification == "excluded":
                excluded.append(item)
            else:
                uncertain.append(item)

        for item in overflow:
            item.pop("heuristic_bucket", None)
            item.pop("heuristic_reasons", None)
            item["reason"] = f"{item['reason']}；超出本轮千问复核上限，暂保留为不确定"
            uncertain.append(item)

        return {
            "confirmed": confirmed,
            "uncertain": uncertain,
            "excluded": excluded,
            "limited": bool(overflow),
            "reviewed_count": len(reviewable),
            "remaining_count": len(overflow),
        }

    def _collect_nearby_texts(
        self,
        dxf_result: DxfParseResult,
        x: float,
        y: float,
        limit: int = 4,
        radius: float = 18000.0,
    ) -> List[str]:
        nearby: List[Tuple[float, str]] = []
        for text in dxf_result.texts:
            tx, ty = self.legend_counter._xy(text.get("insert"))
            distance = self.legend_counter._distance((x, y), (tx, ty))
            if distance > radius:
                continue
            content = " ".join(str(text.get("content", "")).replace("\\P", " ").split())
            if not content:
                continue
            nearby.append((distance, content[:36]))
        nearby.sort(key=lambda item: item[0])
        return [item[1] for item in nearby[:limit]]

    def _active_model_name(self) -> str:
        if self.provider == "qwen" and self.vision_reviewer:
            return self.vision_reviewer.model
        return self.model

    def _active_provider_name(self) -> str:
        if self.provider == "qwen" and self.vision_reviewer:
            return "qwen"
        return "heuristic-preview"

    def _empty_bounds(self) -> Dict[str, float]:
        return {"min_x": 0.0, "max_x": 1.0, "min_y": 0.0, "max_y": 1.0}
