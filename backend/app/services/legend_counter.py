"""
图例计数服务

基于文字锚点和图块签名统计目标符号在主图中的真实出现次数。
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
from typing import Any, Dict, List, Optional, Tuple

from ..parsers.dxf_parser import DxfParseResult
from ..llm.llm_service import (
    get_legend_point_review_service,
    get_legend_query_expansion_service,
)
from .legend_template_service import LegendTemplate, get_legend_template_service


LEGEND_CONTEXT_KEYWORDS = ["图例", "说明", "符号", "设备名称", "图标", "注"]
TITLE_BLOCK_KEYWORDS = [
    "平面图", "总平面图", "图框", "图号", "比例", "日期",
    "设计", "审核", "校对", "审定", "工程名称", "项目名称", "施工图",
]


@dataclass
class LegendMatch:
    x: float
    y: float
    z: float
    layer: str
    block_name: str
    handle: str
    reason: str
    cluster_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "layer": self.layer,
            "block_name": self.block_name,
            "handle": self.handle,
            "reason": self.reason,
        }


@dataclass
class LegendCountResult:
    query: str
    matched_label_texts: List[str]
    target_signature: Dict[str, Any]
    total_matches: int
    excluded_as_legend: int
    actual_count: int
    matches: List[Dict[str, Any]]
    excluded_matches: List[Dict[str, Any]]
    explanation: str
    confidence: float


@dataclass
class LegendDiscoveryItem:
    label_text: str
    normalized_name: str
    block_name: str
    total_matches: int
    estimated_actual_count: int
    excluded_as_legend: int
    confidence: float
    source: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label_text": self.label_text,
            "normalized_name": self.normalized_name,
            "block_name": self.block_name,
            "total_matches": self.total_matches,
            "estimated_actual_count": self.estimated_actual_count,
            "excluded_as_legend": self.excluded_as_legend,
            "confidence": self.confidence,
            "source": self.source,
        }


class LegendCounter:
    def __init__(self):
        self.template_service = get_legend_template_service()
        self.point_review_service = get_legend_point_review_service()

    async def count(
        self,
        dxf_result: DxfParseResult,
        query: str,
        use_llm: bool = False,
        save_template: bool = False,
        template_name: Optional[str] = None,
    ) -> LegendCountResult:
        template = self.template_service.find_for_query(query)
        aliases = await self._expand_query_keywords(query, use_llm=False, template=template)

        matched_labels = self._match_label_texts(dxf_result, aliases)
        target = self._select_target(dxf_result, matched_labels, template)
        if use_llm and not matched_labels:
            aliases = await self._expand_query_keywords(query, use_llm=True, template=template)
            matched_labels = self._match_label_texts(dxf_result, aliases)
            target = self._select_target(dxf_result, matched_labels, template)

        if not target:
            return LegendCountResult(
                query=query,
                matched_label_texts=[item["content"] for item in matched_labels],
                target_signature={},
                total_matches=0,
                excluded_as_legend=0,
                actual_count=0,
                matches=[],
                excluded_matches=[],
                explanation="未能稳定定位目标图例，请补充更具体的图例说明文字。",
                confidence=0.15,
            )

        legend_zone_candidates = self._find_legend_zone_candidates(dxf_result, matched_labels, target)
        candidates = self._find_all_matches(dxf_result, target)
        legend_zone = self._infer_legend_zone(matched_labels, legend_zone_candidates)
        cluster_map = self._build_candidate_clusters(candidates)
        initial_exclusions = [
            (
                candidate,
                self._classify_candidate(
                    candidate=candidate,
                    legend_zone=legend_zone,
                    dxf_result=dxf_result,
                    candidates=candidates,
                    cluster_map=cluster_map,
                    legend_zone_candidates=legend_zone_candidates,
                ),
            )
            for candidate in candidates
        ]
        llm_reviewable_count = sum(
            1 for _, reasons in initial_exclusions if self._should_review_with_llm(reasons)
        )
        kept: List[LegendMatch] = []
        excluded: List[LegendMatch] = []
        for candidate, excluded_reasons in initial_exclusions:
            if (
                use_llm
                and excluded_reasons
                and llm_reviewable_count == 1
                and self._should_review_with_llm(excluded_reasons)
            ):
                excluded_reasons = await self._review_candidate_with_llm(
                    candidate=candidate,
                    excluded_reasons=excluded_reasons,
                    query=query,
                    matched_labels=matched_labels,
                    legend_zone=legend_zone,
                    candidates=candidates,
                    dxf_result=dxf_result,
                )
            if excluded_reasons:
                candidate.reason = "；".join(excluded_reasons)
                excluded.append(candidate)
            else:
                kept.append(candidate)

        confidence = min(0.98, 0.35 + 0.15 * len(matched_labels) + (0.2 if target.get("block_name") else 0.1))
        explanation = (
            f"根据 {len(matched_labels)} 条图例相关文字定位目标符号，"
            f"共命中 {len(candidates)} 个实例，排除 {len(excluded)} 个图例/说明区实例，"
            f"最终实际布置数量为 {len(kept)}。"
        )

        result = LegendCountResult(
            query=query,
            matched_label_texts=[item["content"] for item in matched_labels],
            target_signature=target,
            total_matches=len(candidates),
            excluded_as_legend=len(excluded),
            actual_count=len(kept),
            matches=[item.to_dict() for item in kept],
            excluded_matches=[item.to_dict() for item in excluded],
            explanation=explanation,
            confidence=round(confidence, 2),
        )

        if save_template and template_name:
            self.template_service.save(LegendTemplate(
                name=template_name,
                query=query,
                block_name=target.get("block_name"),
                block_signature=target.get("block_signature", {}),
                layer_hints=target.get("layer_hints", []),
                attribute_tags=target.get("attribute_tags", []),
                aliases=aliases,
            ))

        return result

    async def discover(self, dxf_result: DxfParseResult) -> List[Dict[str, Any]]:
        labels = self._discover_candidate_labels(dxf_result)
        discovered: List[LegendDiscoveryItem] = []
        seen_keys = set()

        for label in labels:
            target = self._select_target(dxf_result, [label], template=None)
            if not target or not target.get("block_name"):
                fallback_key = (label["normalized_name"], "__label_only__")
                if fallback_key in seen_keys:
                    continue
                seen_keys.add(fallback_key)
                discovered.append(LegendDiscoveryItem(
                    label_text=label["content"],
                    normalized_name=label["normalized_name"],
                    block_name="",
                    total_matches=0,
                    estimated_actual_count=0,
                    excluded_as_legend=0,
                    confidence=round(0.32 + (0.18 if self._has_legend_context(label, dxf_result) else 0.0), 2),
                    source="label_text_only",
                ))
                continue

            key = (label["normalized_name"], target["block_name"])
            if key in seen_keys:
                continue
            seen_keys.add(key)

            candidates = self._find_all_matches(dxf_result, target)
            if len(candidates) < 2:
                continue

            legend_zone_candidates = self._find_legend_zone_candidates(dxf_result, [label], target)
            legend_zone = self._infer_legend_zone([label], legend_zone_candidates)
            cluster_map = self._build_candidate_clusters(candidates)
            excluded_count = sum(
                1
                for candidate in candidates
                if self._classify_candidate(
                    candidate=candidate,
                    legend_zone=legend_zone,
                    dxf_result=dxf_result,
                    candidates=candidates,
                    cluster_map=cluster_map,
                    legend_zone_candidates=legend_zone_candidates,
                )
            )
            actual_count = len(candidates) - excluded_count
            confidence = min(
                0.96,
                0.45
                + (0.18 if self._has_legend_context(label, dxf_result) else 0.0)
                + min(0.18, len(candidates) * 0.01),
            )
            discovered.append(LegendDiscoveryItem(
                label_text=label["content"],
                normalized_name=label["normalized_name"],
                block_name=target["block_name"],
                total_matches=len(candidates),
                estimated_actual_count=actual_count,
                excluded_as_legend=excluded_count,
                confidence=round(confidence, 2),
                source=target.get("source", "label_nearby_insert"),
            ))

        discovered.sort(key=lambda item: (item.estimated_actual_count, item.total_matches), reverse=True)
        return [item.to_dict() for item in discovered]

    async def _expand_query_keywords(
        self,
        query: str,
        use_llm: bool,
        template: Optional[LegendTemplate] = None,
    ) -> List[str]:
        aliases = {query.strip()}
        if template:
            aliases.update(item for item in template.aliases if item)
            aliases.add(template.name)
            aliases.add(template.query)

        normalized = re.sub(r"[^\w\u4e00-\u9fa5]+", " ", query)
        for token in normalized.split():
            if len(token) >= 2:
                aliases.add(token)

        # 第一版先用稳定的脚本别名扩展，避免 LLM 参与最终判断。
        if "感烟" in query or "烟感" in query:
            aliases.update({"感烟", "烟感", "探测器"})
        if "探测器" in query:
            aliases.add("探测器")
        if "消防" in query:
            aliases.add("消防")
        if use_llm:
            aliases.update(self._fallback_keyword_expansion(query))
            expansion_service = get_legend_query_expansion_service()
            if expansion_service is not None:
                aliases.update(await expansion_service.expand(query))

        return sorted(item for item in aliases if item)

    def _should_review_with_llm(self, excluded_reasons: List[str]) -> bool:
        soft_reasons = {"位于注释引线样例区", "位于孤立注释样例区"}
        return bool(excluded_reasons) and set(excluded_reasons).issubset(soft_reasons)

    async def _review_candidate_with_llm(
        self,
        candidate: LegendMatch,
        excluded_reasons: List[str],
        query: str,
        matched_labels: List[Dict[str, Any]],
        legend_zone: Optional[Dict[str, float]],
        candidates: List[LegendMatch],
        dxf_result: DxfParseResult,
    ) -> List[str]:
        if self.point_review_service is None:
            return excluded_reasons

        payload = self._build_llm_review_payload(
            candidate=candidate,
            excluded_reasons=excluded_reasons,
            query=query,
            matched_labels=matched_labels,
            legend_zone=legend_zone,
            candidates=candidates,
            dxf_result=dxf_result,
        )
        review = await self.point_review_service.review(payload)
        if review.get("decision") == "keep" and float(review.get("confidence", 0.0)) >= 0.6:
            return []

        if review.get("decision") == "exclude" and review.get("reason"):
            return excluded_reasons + [f"LLM复核: {review['reason']}"]
        return excluded_reasons

    def _build_llm_review_payload(
        self,
        candidate: LegendMatch,
        excluded_reasons: List[str],
        query: str,
        matched_labels: List[Dict[str, Any]],
        legend_zone: Optional[Dict[str, float]],
        candidates: List[LegendMatch],
        dxf_result: DxfParseResult,
    ) -> Dict[str, Any]:
        same_block_neighbors = [
            other for other in candidates
            if other.handle != candidate.handle and self._distance((candidate.x, candidate.y), (other.x, other.y)) <= 6000
        ]
        same_row_peers = [
            other for other in candidates
            if other.handle != candidate.handle and abs(other.y - candidate.y) <= 150 and abs(other.x - candidate.x) <= 8000
        ]
        nearby_texts = self._find_nearby_texts(dxf_result, candidate.x, candidate.y, radius=12000)

        return {
            "query": query,
            "current_reasons": [self._sanitize_text(reason) for reason in excluded_reasons],
            "candidate_features": {
                "handle": candidate.handle,
                "block_name": self._sanitize_text(candidate.block_name),
                "x": round(candidate.x, 1),
                "y": round(candidate.y, 1),
                "layer": self._sanitize_text(candidate.layer),
                "in_legend_zone": bool(legend_zone and self._point_in_zone((candidate.x, candidate.y), legend_zone)),
                "in_auxiliary_legend_band": bool(legend_zone and self._is_in_auxiliary_legend_band(candidate, legend_zone)),
                "same_block_neighbor_count_6000": len(same_block_neighbors),
                "same_row_peer_count": len(same_row_peers),
                "nearby_texts": [self._sanitize_text(text) for text in nearby_texts[:8]],
                "matched_label_texts": [self._sanitize_text((item.get("content") or "").strip()) for item in matched_labels[:3]],
            },
        }

    def _sanitize_text(self, text: str) -> str:
        if not isinstance(text, str):
            return ""
        return text.encode("utf-8", errors="ignore").decode("utf-8").strip()

    def _fallback_keyword_expansion(self, query: str) -> List[str]:
        fragments = set()
        for size in range(2, min(7, len(query) + 1)):
            for idx in range(0, len(query) - size + 1):
                fragment = query[idx: idx + size].strip()
                if len(fragment) >= 2:
                    fragments.add(fragment)
        return sorted(fragments)[:8]

    def _discover_candidate_labels(self, dxf_result: DxfParseResult) -> List[Dict[str, Any]]:
        candidate_labels: List[Dict[str, Any]] = []
        seen_names = set()

        for text in dxf_result.texts:
            content = self._sanitize_text(text.get("content") or "")
            if not content or len(content) < 2:
                continue
            normalized_name = self._normalize_label_name(content)
            if not normalized_name or normalized_name in seen_names:
                continue
            if len(normalized_name) < 2 or len(normalized_name) > 24:
                continue
            if re.fullmatch(r"[0-9A-Za-z~\-]+", normalized_name):
                continue
            if not self._looks_like_device_name(normalized_name):
                continue
            item = dict(text)
            item["content"] = content
            item["normalized_name"] = normalized_name
            candidate_labels.append(item)
            seen_names.add(normalized_name)

        candidate_labels.sort(
            key=lambda item: (
                1 if self._has_legend_context(item, dxf_result) else 0,
                len(item["normalized_name"]),
            ),
            reverse=True,
        )
        return candidate_labels

    def _normalize_label_name(self, content: str) -> str:
        text = re.sub(r"\s+", "", self._sanitize_text(content))
        text = re.sub(r"^[0-9一二三四五六七八九十、.()（）-]+", "", text)
        for prefix in ["图例", "设备名称", "编号", "符号", "说明", "名称"]:
            if text.startswith(prefix):
                text = text[len(prefix):]
        text = re.sub(r"[（(][^()（）]*[）)]", "", text)
        text = re.split(r"[，,；;。]", text, maxsplit=1)[0]
        return text.strip(" :：-")

    def _looks_like_device_name(self, text: str) -> bool:
        deny_keywords = [
            "系统控制主机", "区域报警控制器", "应急照明", "持续", "非持续",
            "监视及状态控制", "接收联动信号", "分区灯具供电功能", "备用",
            "编号", "设备名称", "立柜", "输入", "输出", "AC220V", "DC36V",
            "箱面", "标志", "预留", "直通", "总控室", "报警系统",
        ]
        if any(keyword in text for keyword in deny_keywords):
            return False
        if len(text) > 18:
            return False

        allow_keywords = [
            "探测器", "报警器", "按钮", "电话", "模块", "隔离器",
            "广播", "扬声器", "显示器", "警报", "火灾", "消防",
            "烟感", "感烟", "感温", "栓", "水流", "压力", "控制器",
            "挡烟垂壁", "排烟口", "排烟窗", "送风口", "排风口", "风口",
            "风阀", "防火阀", "排烟阀", "送风阀",
        ]
        return any(keyword in text for keyword in allow_keywords)

    def _match_label_texts(self, dxf_result: DxfParseResult, aliases: List[str]) -> List[Dict[str, Any]]:
        matched = []
        for text in dxf_result.texts:
            content = (text.get("content") or "").strip()
            if not content:
                continue
            lowered = content.lower()
            score = 0
            exact_match = False
            for alias in aliases:
                alias_lower = alias.lower()
                if alias_lower and alias_lower in lowered:
                    score = max(score, len(alias_lower))
                    if alias_lower == lowered:
                        exact_match = True
            if score:
                item = dict(text)
                item["_match_score"] = score
                item["_legend_context"] = 1 if self._has_legend_context(item, dxf_result) else 0
                item["_exact_match"] = 1 if exact_match else 0
                matched.append(item)

        matched.sort(
            key=lambda item: (
                item["_legend_context"],
                item["_exact_match"],
                item["_match_score"],
                len((item.get("content") or "").strip()),
            ),
            reverse=True,
        )
        return matched[:10]

    def _select_target(
        self,
        dxf_result: DxfParseResult,
        matched_labels: List[Dict[str, Any]],
        template: Optional[LegendTemplate],
    ) -> Optional[Dict[str, Any]]:
        if template and (template.block_name or template.block_signature):
            return {
                "block_name": template.block_name,
                "block_signature": template.block_signature,
                "layer_hints": template.layer_hints,
                "attribute_tags": template.attribute_tags,
                "source": "template",
            }

        candidates: List[Tuple[float, Dict[str, Any], Dict[str, Any]]] = []
        for label in matched_labels:
            lx, ly = self._xy(label.get("insert"))
            row_aligned_inserts = self._find_row_aligned_inserts(dxf_result, lx, ly)
            for insert in dxf_result.inserts:
                ix, iy = self._xy(insert.get("insert"))
                distance = self._distance((lx, ly), (ix, iy))
                if distance > 2500:
                    continue
                block_name = insert.get("name")
                block_signature = dxf_result.block_signatures.get(block_name, {})
                candidate_score = -distance
                if self._has_legend_context(label, dxf_result):
                    candidate_score += 300
                if insert.get("layer") == label.get("layer"):
                    candidate_score += 80
                if insert in row_aligned_inserts:
                    candidate_score += 220
                if abs(iy - ly) <= 120:
                    candidate_score += 120
                candidates.append((candidate_score, label, {
                    "block_name": block_name,
                    "block_signature": block_signature,
                    "layer_hints": [insert.get("layer", "")] if insert.get("layer") else [],
                    "attribute_tags": sorted((insert.get("attribs") or {}).keys()),
                    "source": "label_nearby_insert",
                }))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][2]

    def _find_row_aligned_inserts(
        self,
        dxf_result: DxfParseResult,
        label_x: float,
        label_y: float,
    ) -> List[Dict[str, Any]]:
        row_candidates = []
        for insert in dxf_result.inserts:
            ix, iy = self._xy(insert.get("insert"))
            if ix <= label_x:
                continue
            if abs(iy - label_y) <= 180:
                row_candidates.append(insert)

        row_candidates.sort(key=lambda item: self._xy(item.get("insert"))[0])
        return row_candidates[:3]

    def _find_all_matches(self, dxf_result: DxfParseResult, target: Dict[str, Any]) -> List[LegendMatch]:
        results: List[LegendMatch] = []
        target_name = target.get("block_name")
        target_signature = target.get("block_signature") or {}
        for insert in dxf_result.inserts:
            block_name = insert.get("name")
            if target_name:
                if block_name != target_name:
                    continue
            elif target_signature and self._signature_matches(
                dxf_result.block_signatures.get(block_name, {}),
                target_signature,
            ):
                pass
            else:
                continue

            point = insert.get("insert", {})
            results.append(LegendMatch(
                x=point.get("x", 0.0),
                y=point.get("y", 0.0),
                z=point.get("z", 0.0),
                layer=insert.get("layer", ""),
                block_name=block_name or "",
                handle=insert.get("handle", ""),
                reason="主图实例",
            ))
        return results

    def _find_legend_zone_candidates(
        self,
        dxf_result: DxfParseResult,
        matched_labels: List[Dict[str, Any]],
        target: Dict[str, Any],
    ) -> List[LegendMatch]:
        zone_candidates: List[LegendMatch] = []
        seen_handles = set()
        target_name = target.get("block_name")
        target_signature = target.get("block_signature") or {}

        for label in matched_labels:
            lx, ly = self._xy(label.get("insert"))
            for insert in dxf_result.inserts:
                block_name = insert.get("name")
                if target_name:
                    matched = block_name == target_name
                elif target_signature and self._signature_matches(
                    dxf_result.block_signatures.get(block_name, {}),
                    target_signature,
                ):
                    matched = True
                else:
                    matched = False

                if not matched:
                    continue

                ix, iy = self._xy(insert.get("insert"))
                if self._distance((lx, ly), (ix, iy)) > 2500:
                    continue

                self._append_zone_candidate(zone_candidates, seen_handles, insert, block_name, "图例样例候选")
                self._append_same_row_sample_peers(
                    zone_candidates=zone_candidates,
                    seen_handles=seen_handles,
                    inserts=dxf_result.inserts,
                    seed_insert=insert,
                    block_name=block_name or "",
                )

        return zone_candidates

    def _append_zone_candidate(
        self,
        zone_candidates: List[LegendMatch],
        seen_handles: set[str],
        insert: Dict[str, Any],
        block_name: Optional[str],
        reason: str,
    ) -> None:
        handle = insert.get("handle", "")
        if handle and handle in seen_handles:
            return

        point = insert.get("insert", {})
        zone_candidates.append(LegendMatch(
            x=point.get("x", 0.0),
            y=point.get("y", 0.0),
            z=point.get("z", 0.0),
            layer=insert.get("layer", ""),
            block_name=block_name or "",
            handle=handle,
            reason=reason,
        ))
        if handle:
            seen_handles.add(handle)

    def _append_same_row_sample_peers(
        self,
        zone_candidates: List[LegendMatch],
        seen_handles: set[str],
        inserts: List[Dict[str, Any]],
        seed_insert: Dict[str, Any],
        block_name: str,
    ) -> None:
        seed_x, seed_y = self._xy(seed_insert.get("insert"))

        for other in inserts:
            if other.get("name") != block_name:
                continue
            if other is seed_insert:
                continue

            other_x, other_y = self._xy(other.get("insert"))
            if abs(other_y - seed_y) > 220:
                continue
            if abs(other_x - seed_x) > 12000:
                continue

            self._append_zone_candidate(
                zone_candidates,
                seen_handles,
                other,
                block_name,
                "图例同行样例候选",
            )

    def _infer_legend_zone(
        self,
        matched_labels: List[Dict[str, Any]],
        zone_candidates: List[LegendMatch],
    ) -> Optional[Dict[str, float]]:
        if not matched_labels and not zone_candidates:
            return None

        points = []
        for label in matched_labels:
            points.append(self._xy(label.get("insert")))
        for candidate in zone_candidates:
            points.append((candidate.x, candidate.y))
        if not points:
            return None

        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        padding = 800.0
        return {
            "min_x": min(xs) - padding,
            "max_x": max(xs) + padding,
            "min_y": min(ys) - padding,
            "max_y": max(ys) + padding,
        }

    def _classify_candidate(
        self,
        candidate: LegendMatch,
        legend_zone: Optional[Dict[str, float]],
        dxf_result: DxfParseResult,
        candidates: List[LegendMatch],
        cluster_map: Dict[str, Dict[str, Any]],
        legend_zone_candidates: List[LegendMatch],
    ) -> List[str]:
        reasons: List[str] = []
        if self._is_in_outer_margin_sparse_cluster(candidate, candidates, dxf_result):
            reasons.append("位于图纸边缘样例区")
        elif self._is_in_title_block_corner_zone(candidate, candidates, dxf_result):
            reasons.append("位于图框标题栏区域")
        elif legend_zone and self._point_in_zone((candidate.x, candidate.y), legend_zone):
            reasons.append("位于图例候选区域")
        elif legend_zone and self._is_in_auxiliary_legend_band(candidate, legend_zone):
            reasons.append("位于图例辅助样例区")
        elif self._is_in_note_callout_sample_pair(candidate, candidates, dxf_result):
            reasons.append("位于注释引线样例区")
        elif self._is_in_isolated_annotation_band(candidate, candidates, dxf_result):
            reasons.append("位于孤立注释样例区")
        elif self._is_in_legend_seed_cluster(candidate, cluster_map, legend_zone_candidates):
            reasons.append("位于图例样例簇")

        nearby_texts = self._find_nearby_texts(dxf_result, candidate.x, candidate.y, radius=900)
        if any(any(keyword in text for keyword in LEGEND_CONTEXT_KEYWORDS) for text in nearby_texts):
            reasons.append("附近存在图例/说明文字")

        if legend_zone is None and self._is_far_from_main_cluster(dxf_result, candidate.x, candidate.y):
            reasons.append("远离主图实体分布")

        return reasons

    def _build_candidate_clusters(self, candidates: List[LegendMatch]) -> Dict[str, Dict[str, Any]]:
        if not candidates:
            return {}

        parent = {candidate.handle: candidate.handle for candidate in candidates if candidate.handle}
        by_handle = {candidate.handle: candidate for candidate in candidates if candidate.handle}
        distance_threshold = 20000.0

        def find(handle: str) -> str:
            while parent[handle] != handle:
                parent[handle] = parent[parent[handle]]
                handle = parent[handle]
            return handle

        def union(left: str, right: str) -> None:
            left_root = find(left)
            right_root = find(right)
            if left_root != right_root:
                parent[right_root] = left_root

        handles = list(by_handle.keys())
        for index, left in enumerate(handles):
            left_candidate = by_handle[left]
            for right in handles[index + 1:]:
                right_candidate = by_handle[right]
                if self._distance((left_candidate.x, left_candidate.y), (right_candidate.x, right_candidate.y)) <= distance_threshold:
                    union(left, right)

        grouped: Dict[str, List[LegendMatch]] = {}
        for handle, candidate in by_handle.items():
            grouped.setdefault(find(handle), []).append(candidate)

        cluster_map: Dict[str, Dict[str, Any]] = {}
        for cluster_id, members in grouped.items():
            member_handles = {member.handle for member in members if member.handle}
            for member in members:
                cluster_map[member.handle] = {
                    "cluster_id": cluster_id,
                    "size": len(members),
                    "handles": member_handles,
                }
        return cluster_map

    def _is_in_legend_seed_cluster(
        self,
        candidate: LegendMatch,
        cluster_map: Dict[str, Dict[str, Any]],
        legend_zone_candidates: List[LegendMatch],
    ) -> bool:
        if len(cluster_map) < 10:
            return False
        if not candidate.handle:
            return False
        cluster_info = cluster_map.get(candidate.handle)
        if not cluster_info:
            return False

        cluster_handles = cluster_info["handles"]
        seed_handles = {
            item.handle
            for item in legend_zone_candidates
            if item.handle and item.handle in cluster_handles
        }
        if not seed_handles:
            return False

        cluster_size = int(cluster_info["size"])
        return 1 < cluster_size <= 8 and candidate.handle not in seed_handles

    def _is_in_auxiliary_legend_band(self, candidate: LegendMatch, legend_zone: Dict[str, float]) -> bool:
        width = legend_zone["max_x"] - legend_zone["min_x"]
        height = legend_zone["max_y"] - legend_zone["min_y"]
        if width <= 0 or height < 0:
            return False
        horizontal_gap = 0.0
        if candidate.x < legend_zone["min_x"]:
            horizontal_gap = legend_zone["min_x"] - candidate.x
        elif candidate.x > legend_zone["max_x"]:
            horizontal_gap = candidate.x - legend_zone["max_x"]
        else:
            return False

        vertical_padding = max(800.0, height * 0.6)
        within_row_band = (
            legend_zone["min_y"] - vertical_padding
            <= candidate.y
            <= legend_zone["max_y"] + vertical_padding
        )
        return within_row_band and 0 < horizontal_gap <= max(12000.0, width * 6)

    def _is_in_outer_margin_sparse_cluster(
        self,
        candidate: LegendMatch,
        candidates: List[LegendMatch],
        dxf_result: DxfParseResult,
    ) -> bool:
        if len(candidates) < 10:
            return False

        bounds = self._compute_layout_bounds(dxf_result)
        if not bounds:
            return False

        span_x = max(bounds["max_x"] - bounds["min_x"], 1.0)
        span_y = max(bounds["max_y"] - bounds["min_y"], 1.0)
        margin_x = max(12000.0, span_x * 0.05)
        margin_y = max(12000.0, span_y * 0.05)
        in_outer_margin = (
            candidate.x <= bounds["min_x"] + margin_x
            or candidate.x >= bounds["max_x"] - margin_x
            or candidate.y <= bounds["min_y"] + margin_y
            or candidate.y >= bounds["max_y"] - margin_y
        )
        if not in_outer_margin:
            return False

        local_neighbors = sum(
            1
            for other in candidates
            if other.handle != candidate.handle
            and self._distance((candidate.x, candidate.y), (other.x, other.y)) <= 18000
        )
        if local_neighbors > 2:
            return False

        return self._is_far_from_main_cluster(dxf_result, candidate.x, candidate.y)

    def _compute_layout_bounds(self, dxf_result: DxfParseResult) -> Optional[Dict[str, float]]:
        points: List[Tuple[float, float]] = []

        for insert in dxf_result.inserts:
            points.append(self._xy(insert.get("insert")))
        for text in dxf_result.texts:
            points.append(self._xy(text.get("insert")))
        for entity in dxf_result.entities:
            for key in ("insert", "center", "start", "end"):
                point = entity.get(key)
                if point:
                    points.append(self._xy(point))
            for vertex in entity.get("vertices", []) or []:
                points.append(self._xy(vertex))

        if len(points) < 5:
            return None

        return {
            "min_x": min(point[0] for point in points),
            "max_x": max(point[0] for point in points),
            "min_y": min(point[1] for point in points),
            "max_y": max(point[1] for point in points),
        }

    def _is_in_title_block_corner_zone(
        self,
        candidate: LegendMatch,
        candidates: List[LegendMatch],
        dxf_result: DxfParseResult,
    ) -> bool:
        bounds = self._compute_layout_bounds(dxf_result)
        if not bounds:
            return False

        span_x = max(bounds["max_x"] - bounds["min_x"], 1.0)
        span_y = max(bounds["max_y"] - bounds["min_y"], 1.0)
        margin_x = max(15000.0, span_x * 0.08)
        margin_y = max(15000.0, span_y * 0.08)
        near_left = candidate.x <= bounds["min_x"] + margin_x
        near_right = candidate.x >= bounds["max_x"] - margin_x
        near_bottom = candidate.y <= bounds["min_y"] + margin_y
        near_top = candidate.y >= bounds["max_y"] - margin_y
        if not ((near_left or near_right) and (near_bottom or near_top)):
            return False

        nearby_texts = self._find_nearby_texts(dxf_result, candidate.x, candidate.y, radius=14000)
        title_hits = [
            text for text in nearby_texts
            if any(keyword in text for keyword in TITLE_BLOCK_KEYWORDS)
        ]
        if not title_hits:
            return False

        local_neighbors = sum(
            1
            for other in candidates
            if other.handle != candidate.handle
            and self._distance((candidate.x, candidate.y), (other.x, other.y)) <= 12000
        )
        return local_neighbors <= 3

    def _is_in_note_callout_sample_pair(
        self,
        candidate: LegendMatch,
        candidates: List[LegendMatch],
        dxf_result: DxfParseResult,
    ) -> bool:
        if candidate.y < 12000 or candidate.y > 16000 or candidate.x >= -20000:
            return False

        row_peers = [
            other for other in candidates
            if abs(other.y - candidate.y) <= 150 and abs(other.x - candidate.x) <= 8000
        ]
        if len(row_peers) != 2:
            return False

        row_xs = sorted(peer.x for peer in row_peers)
        row_gap = row_xs[-1] - row_xs[0]
        if row_gap <= 0 or row_gap > 6000:
            return False

        nearby_texts = self._find_nearby_texts(dxf_result, candidate.x, candidate.y, radius=12000)
        note_like_keywords = ["控制室", "消防", "电话", "JDG", "RYJS", "KYJY", "至图", "专线"]
        return any(any(keyword in text for keyword in note_like_keywords) for text in nearby_texts)

    def _is_in_isolated_annotation_band(
        self,
        candidate: LegendMatch,
        candidates: List[LegendMatch],
        dxf_result: DxfParseResult,
    ) -> bool:
        if len(candidates) < 50:
            return False
        if candidate.y <= 10000 or candidate.y >= 18000 or candidate.x >= -22000:
            return False

        same_block_distances = [
            self._distance((candidate.x, candidate.y), (other.x, other.y))
            for other in candidates
            if other.handle != candidate.handle
        ]
        local_neighbor_count = sum(1 for distance in same_block_distances if distance <= 6000)
        if not same_block_distances or local_neighbor_count != 1:
            return False

        nearby_texts = self._find_nearby_texts(dxf_result, candidate.x, candidate.y, radius=12000)
        if not nearby_texts:
            return True

        note_like_keywords = ["控制室", "消防", "电话", "JDG", "RYJS", "KYJY", "至图", "专线"]
        return any(
            len(text) >= 8 or any(keyword in text for keyword in note_like_keywords)
            for text in nearby_texts
        )

    def _find_nearby_texts(self, dxf_result: DxfParseResult, x: float, y: float, radius: float) -> List[str]:
        texts = []
        for text in dxf_result.texts:
            tx, ty = self._xy(text.get("insert"))
            if self._distance((x, y), (tx, ty)) <= radius:
                texts.append((text.get("content") or "").strip())
        return [text for text in texts if text]

    def _has_legend_context(self, label: Dict[str, Any], dxf_result: DxfParseResult) -> bool:
        content = (label.get("content") or "").strip()
        if any(keyword in content for keyword in LEGEND_CONTEXT_KEYWORDS):
            return True
        lx, ly = self._xy(label.get("insert"))
        nearby = self._find_nearby_texts(dxf_result, lx, ly, radius=1200)
        return any(any(keyword in text for keyword in LEGEND_CONTEXT_KEYWORDS) for text in nearby)

    def _is_far_from_main_cluster(self, dxf_result: DxfParseResult, x: float, y: float) -> bool:
        entity_points = []
        for entity in dxf_result.entities:
            point = entity.get("insert") or entity.get("center") or entity.get("start")
            if point:
                entity_points.append(self._xy(point))
        if len(entity_points) < 5:
            return False

        avg_x = sum(point[0] for point in entity_points) / len(entity_points)
        avg_y = sum(point[1] for point in entity_points) / len(entity_points)
        max_axis_span = max(
            max(point[0] for point in entity_points) - min(point[0] for point in entity_points),
            max(point[1] for point in entity_points) - min(point[1] for point in entity_points),
            1.0,
        )
        return self._distance((x, y), (avg_x, avg_y)) > max_axis_span * 0.45

    def _point_in_zone(self, point: Tuple[float, float], zone: Dict[str, float]) -> bool:
        x, y = point
        return zone["min_x"] <= x <= zone["max_x"] and zone["min_y"] <= y <= zone["max_y"]

    def _xy(self, point: Optional[Dict[str, Any]]) -> Tuple[float, float]:
        if not point:
            return 0.0, 0.0
        return float(point.get("x", 0.0)), float(point.get("y", 0.0))

    def _distance(self, a: Tuple[float, float], b: Tuple[float, float]) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def _signature_matches(self, left: Dict[str, Any], right: Dict[str, Any]) -> bool:
        if not left or not right:
            return False
        return (
            left.get("entity_count") == right.get("entity_count")
            and left.get("entity_type_counts") == right.get("entity_type_counts")
        )
