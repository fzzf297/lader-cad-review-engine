"""
图例模板服务

第一版使用 JSON 持久化轻量模板，支持保存与复用。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from ..core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class LegendTemplate:
    name: str
    query: str
    block_name: Optional[str] = None
    block_signature: Dict[str, object] = field(default_factory=dict)
    layer_hints: List[str] = field(default_factory=list)
    attribute_tags: List[str] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)


class LegendTemplateService:
    def __init__(self, storage_path: Optional[str] = None):
        base_dir = Path(settings.UPLOAD_DIR)
        self.storage_path = Path(storage_path) if storage_path else base_dir / "legend_templates.json"
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._templates: Dict[str, LegendTemplate] = {}
        self._load()

    def _load(self) -> None:
        if not self.storage_path.exists():
            return
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("加载图例模板失败: %s", exc)
            return

        for item in data:
            try:
                template = LegendTemplate(**item)
            except TypeError as exc:
                logger.warning("跳过损坏图例模板 %s: %s", item, exc)
                continue
            self._templates[template.name] = template

    def _save(self) -> None:
        payload = [asdict(template) for template in self._templates.values()]
        self.storage_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def save(self, template: LegendTemplate) -> LegendTemplate:
        self._templates[template.name] = template
        self._save()
        return template

    def list(self) -> List[LegendTemplate]:
        return list(self._templates.values())

    def find_for_query(self, query: str) -> Optional[LegendTemplate]:
        query_lower = query.lower()
        for template in self._templates.values():
            candidates = [template.query, template.name, *template.aliases]
            if any(candidate and candidate.lower() in query_lower for candidate in candidates):
                return template
        return None


_legend_template_service: Optional[LegendTemplateService] = None


def get_legend_template_service(storage_path: Optional[str] = None) -> LegendTemplateService:
    if storage_path is not None:
        return LegendTemplateService(storage_path=storage_path)

    global _legend_template_service
    if _legend_template_service is None:
        _legend_template_service = LegendTemplateService()
    return _legend_template_service
