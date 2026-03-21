"""
LLM 审核服务 - 基于阿里云千问 API
"""
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
import json
import logging
import re

from ..core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class LLMReviewResult:
    """LLM 审核结果"""
    overall_assessment: str = ""
    score: float = 0
    issues: List[Dict] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    raw_response: str = ""
    token_usage: Dict = field(default_factory=dict)


# 系统提示词
SYSTEM_PROMPT = """
你是一位专业的建筑施工图审核专家，精通中国建筑制图标准：
- GB/T 50001-2017 房屋建筑制图统一标准
- GB/T 50104-2010 建筑制图标准
- 各地方建筑规范

你的任务是审核 DWG 施工图数据，识别不符合规范的问题并给出专业建议。
请以结构化 JSON 格式输出审核结果。
"""

# 审核提示词模板
REVIEW_PROMPT_TEMPLATE = """
## 任务
请审核以下 DWG 施工图数据，检查是否符合建筑制图规范。

## 图纸数据摘要
{data_summary}

## 审核要求
请从以下维度进行审核：

1. **图层规范**
   - 图层命名是否符合国标（如：墙体、门窗、标注、尺寸等）
   - 图层分类是否合理
   - 是否存在冗余或缺失图层

2. **图块规范**
   - 门窗等图块命名是否规范
   - 图块属性是否完整（尺寸、材质、编号等）
   - 是否存在未定义的匿名块

3. **标注规范**
   - 尺寸标注样式是否统一
   - 文字高度是否符合出图比例
   - 标注是否完整清晰

4. **设计合理性**（重点）
   - 图纸表达是否完整
   - 是否存在明显的制图错误
   - 是否符合设计深度要求

5. **其他问题**
   - 发现的其他不符合规范的问题

## 输出格式
请按以下 JSON 格式输出：

```json
{
  "overall_assessment": "整体评价（通过/需修改/不通过）",
  "score": 85,
  "issues": [
    {
      "category": "图层规范",
      "severity": "error|warning|info",
      "description": "问题描述",
      "location": "相关图层/实体",
      "suggestion": "修改建议",
      "confidence": 0.95
    }
  ],
  "suggestions": [
    "整体改进建议"
  ]
}
```
"""

LEGEND_QUERY_EXPANSION_PROMPT = """
你只做图例检索扩词，不做计数，不做判断。

用户查询: {query}

输出 JSON:
{{"keywords":["词1","词2","词3"]}}

规则:
- 返回 3 到 6 个中文关键词或常见简称
- 优先保留设备名、简称、同义词
- 不输出解释
- 不输出数量、结论、推理过程
- 不要重复
"""

LEGEND_POINT_REVIEW_PROMPT = """
你在做 CAD 图例计数复核，但你不是最终计数器。
你只负责复核一个“边界候选点”是否应该被排除。

任务:
- 读取输入中的 candidate_features
- 根据 rules 判断该点应保留为主图实例，还是排除为图例/说明/注释样例
- 只能处理单个点，不要推断整张图

核心规则:
1. 位于图例表主区域，一律排除
2. 位于图例辅助样例带，一律排除
3. 与设备名称表/编号表同一行且紧邻表头，排除
4. 仅仅靠近“消防专线电话”“控制室”“线缆型号”等说明文字，不足以单独判定排除
5. 注释引线样例通常成对/成组出现，位于说明带，且附近是说明性文字，不是房间或设备布置文字
6. 无法确定时优先保留，不要过度排除

输出 JSON:
{{"decision":"keep|exclude","confidence":0.0,"reason":"一句简短中文说明"}}

输入:
{payload}
"""

# 合同分析提示词 - 只提取"发包人供应材料设备一览表"
MATERIAL_SUPPLY_LIST_PROMPT = """
## 任务
请从以下建筑合同中找到并解析【发包人供应材料设备一览表】或【甲方供应材料设备表】。

## 合同内容
{contract_content}

## 提取要求
**重要提示**：该表格可能以以下形式存在：
1. 作为合同附件（如"附件1：发包人供应材料设备一览表"）
2. 在合同正文中的独立表格
3. 以文本列表形式存在

请在合同中搜索以下关键词定位表格：
- "发包人供应材料设备一览表"
- "甲方供应材料设备表"
- "发包人供应材料"
- "甲方供应材料"
- "材料设备供应表"
- "材料清单"

找到后，提取每一项材料/设备的详细信息：

1. **item_no**: 序号（1、2、3...）
2. **name**: 材料/设备名称（如：消火栓、管道、阀门等）
3. **specification**: 规格型号（详细的规格、参数、品牌等信息）
4. **unit**: 单位（个、套、米、台、具、部等）
5. **quantity**: 数量（数字或文字描述）
6. **supply_method**: 供应方式（如有说明，如"甲供"、"甲方供应"等）
7. **remarks**: 备注（如品牌要求、特殊说明等）

## 输出格式
请严格按以下 JSON 格式输出：

```json
{
  "material_supply_list": {
    "table_found": true,
    "table_name": "发包人供应材料设备一览表",
    "project_name": "工程名称",
    "location": "施工地点",
    "items": [
      {
        "item_no": "1",
        "name": "消火栓",
        "specification": "组合式消火栓柜，型号SG18B65Z-J",
        "unit": "套",
        "quantity": "12",
        "supply_method": "甲方供应",
        "remarks": "通天河/国标"
      }
    ],
    "summary": {
      "total_items": 33,
      "categories": {
        "消防设备": 10,
        "管道材料": 5,
        "电气设备": 8,
        "监控设备": 1
      }
    }
  }
}
```

注意：
- 如果合同中确实未找到"发包人供应材料设备一览表"，请返回 `{"material_supply_list": {"table_found": false, "items": []}}`
- 保持原文描述的准确性，不要遗漏任何材料/设备
- 规格型号请尽量详细提取，包含技术参数
- 如果某项信息未提及，使用空字符串
"""

# 合同分析提示词 - 只提取施工范围（保留备用）
CONSTRUCTION_SCOPE_PROMPT = """
## 任务
请从以下建筑合同中提取【施工范围】的详细内容。

## 合同内容
{contract_content}

## 表格数据
{tables_content}

## 提取要求
请仔细阅读合同，找到"施工范围"、"工程内容"、"承包范围"等相关章节，提取以下信息：

1. **施工地点/范围**：工程涉及的具体位置、建筑物名称
2. **施工内容清单**：具体的施工项目列表，每项包括：
   - 项目名称
   - 具体内容描述
   - 数量（如有）
   - 单位（如有）
   - 规格/型号（如有）
3. **主要材料/设备**：需要更换或安装的主要材料、设备
4. **施工标准/规范**：遵循的技术标准（如有提及）

## 输出格式
请按以下 JSON 格式输出：

```json
{
  "construction_scope": {
    "project_name": "工程名称",
    "location": "施工地点",
    "buildings": ["涉及建筑1", "涉及建筑2"],
    "summary": "施工范围总体描述",
    "work_items": [
      {
        "item_no": "1",
        "name": "项目名称",
        "description": "详细描述",
        "quantity": "数量",
        "unit": "单位",
        "specification": "规格型号",
        "location": "具体位置"
      }
    ],
    "main_materials": ["主要材料1", "主要材料2"],
    "standards": ["适用标准1", "适用标准2"],
    "original_text": "施工范围原文"
  }
}
```

注意：
- 保持原文描述的准确性，不要遗漏重要信息
- 如果某项信息在合同中未提及，使用空字符串或空数组
- 尽可能详细列出所有施工内容
"""

# 合同分析提示词（完整版）
CONTRACT_ANALYSIS_PROMPT = """
## 任务
请分析以下建筑合同内容，提取关键信息。

## 合同内容
{contract_content}

## 表格数据
{tables_content}

## 输出要求
请按以下 JSON 格式输出：

```json
{
  "project_name": "项目名称",
  "contract_parties": {
    "party_a": "甲方名称",
    "party_b": "乙方名称"
  },
  "work_items": [
    {
      "name": "工作项名称",
      "category": "分类（门窗/管道/电气/土建/装修等）",
      "quantity": 100,
      "unit": "单位（个/米/平方米等）",
      "specification": "规格描述",
      "location": "施工位置",
      "deadline": "时间节点",
      "original_text": "原文引用"
    }
  ],
  "key_terms": [
    {
      "type": "条款类型（工期/付款/验收/质保等）",
      "content": "条款内容",
      "importance": "high/medium/low"
    }
  ],
  "total_amount": 1000000,
  "summary": "合同概要"
}
```
"""


class SummaryGenerator:
    """为 LLM 生成图纸数据摘要"""

    # 门窗关键词
    DOOR_WINDOW_KEYWORDS = ["门", "窗", "DOOR", "WINDOW", "M", "C", "MC"]

    def generate(self, dxf_data: Dict) -> str:
        """生成结构化摘要 JSON"""
        summary = {
            "文件信息": self._summarize_file_info(dxf_data.get("file_info", {})),
            "图层列表": self._summarize_layers(dxf_data.get("layers", {})),
            "图块统计": self._summarize_blocks(dxf_data.get("blocks", {})),
            "实体统计": self._count_entities(dxf_data.get("entities", [])),
            "文字样本": self._extract_text_samples(dxf_data.get("texts", []), limit=20),
            "标注样本": self._extract_dimension_samples(dxf_data.get("dimensions", []), limit=10),
            "门窗识别": self._identify_door_window_blocks(dxf_data.get("blocks", {})),
        }
        return json.dumps(summary, ensure_ascii=False, indent=2)

    def _summarize_file_info(self, file_info: Dict) -> Dict:
        """文件信息摘要"""
        return {
            "DXF版本": file_info.get("dxf_version", "Unknown"),
            "单位": file_info.get("units_name", "未知"),
        }

    def _summarize_layers(self, layers: Dict) -> List[Dict]:
        """图层摘要"""
        result = []
        for name, info in list(layers.items())[:50]:
            result.append({
                "名称": name,
                "颜色": info.get("color"),
                "线型": info.get("linetype"),
                "状态": "关闭" if info.get("off") else "开启"
            })
        return result

    def _summarize_blocks(self, blocks: Dict) -> List[Dict]:
        """图块摘要"""
        result = []
        for name, info in list(blocks.items())[:100]:
            result.append({
                "名称": name,
                "实体数": info.get("entity_count", 0),
                "引用次数": info.get("insert_count", 0),
                "疑似门窗": info.get("is_door_window", False)
            })
        return result

    def _count_entities(self, entities: List) -> Dict[str, int]:
        """实体类型统计"""
        counts = {}
        for entity in entities:
            etype = entity.get("type", "UNKNOWN")
            counts[etype] = counts.get(etype, 0) + 1
        return counts

    def _extract_text_samples(self, texts: List, limit: int = 20) -> List[str]:
        """提取文字样本"""
        samples = []
        for text in texts[:limit]:
            content = text.get("content", "")
            if content and content.strip():
                samples.append(content.strip()[:100])
        return samples

    def _extract_dimension_samples(self, dimensions: List, limit: int = 10) -> List[Dict]:
        """提取标注样本"""
        samples = []
        for dim in dimensions[:limit]:
            samples.append({
                "文字": dim.get("text", ""),
                "样式": dim.get("style", ""),
            })
        return samples

    def _identify_door_window_blocks(self, blocks: Dict) -> Dict:
        """识别门窗图块"""
        door_blocks = []
        window_blocks = []

        for name, info in blocks.items():
            if not info.get("is_door_window"):
                continue

            insert_count = info.get("insert_count", 0)
            name_upper = name.upper()

            # 识别门
            if any(kw in name_upper for kw in ["门", "DOOR", "M"]):
                door_blocks.append({
                    "名称": name,
                    "引用次数": insert_count
                })

            # 识别窗
            if any(kw in name_upper for kw in ["窗", "WINDOW", "C"]):
                window_blocks.append({
                    "名称": name,
                    "引用次数": insert_count
                })

        return {
            "门图块": door_blocks,
            "门总数": sum(b["引用次数"] for b in door_blocks),
            "窗图块": window_blocks,
            "窗总数": sum(b["引用次数"] for b in window_blocks),
        }


class LLMReviewService:
    """LLM 审核服务 - 基于阿里云千问 API"""

    def __init__(
        self,
        api_key: str,
        model: str = "qwen3.5-plus",
        base_url: str = "https://coding.dashscope.aliyuncs.com/v1"
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.summary_generator = SummaryGenerator()

    async def review(self, dxf_data: Dict[str, Any]) -> LLMReviewResult:
        """执行 LLM 审核"""
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("请安装 openai: pip install openai")

        client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

        # 生成数据摘要
        summary = self.summary_generator.generate(dxf_data)

        # 构建提示词
        prompt = REVIEW_PROMPT_TEMPLATE.format(data_summary=summary)

        try:
            # 调用千问 API
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=4096
            )
            # 解析响应
            content = response.choices[0].message.content
            result = self._parse_response(content)

            # 添加 token 使用统计
            result.token_usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
                "model": self.model
            }

            return result

        except Exception as e:
            logger.error(f"LLM API 调用失败: {e}")
            return LLMReviewResult(
                overall_assessment="审核失败",
                score=0,
                issues=[{
                    "category": "系统错误",
                    "severity": "error",
                    "description": f"LLM 审核失败: {str(e)}",
                    "confidence": 1.0
                }]
            )

    def _parse_response(self, content: str) -> LLMReviewResult:
        """解析 LLM 响应"""
        try:
            # 提取 JSON 部分
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start == -1 or json_end == 0:
                raise ValueError("未找到 JSON 内容")

            json_str = content[json_start:json_end]
            data = json.loads(json_str)

            return LLMReviewResult(
                overall_assessment=data.get("overall_assessment", "未知"),
                score=float(data.get("score", 0)),
                issues=data.get("issues", []),
                suggestions=data.get("suggestions", []),
                raw_response=content
            )
        except Exception as e:
            logger.warning(f"LLM 响应解析失败: {e}")
            return LLMReviewResult(
                overall_assessment="解析失败",
                score=0,
                issues=[{
                    "category": "系统错误",
                    "severity": "warning",
                    "description": f"LLM 响应解析失败: {str(e)}",
                    "confidence": 1.0
                }],
                raw_response=content
            )


class LegendQueryExpansionService:
    """图例查询扩词服务，仅用于补充检索关键词。"""

    def __init__(
        self,
        api_key: str,
        model: str = "qwen3.5-plus",
        base_url: str = "https://coding.dashscope.aliyuncs.com/v1",
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    async def expand(self, query: str) -> List[str]:
        try:
            from openai import AsyncOpenAI
        except ImportError:
            logger.warning("openai 依赖不可用，图例扩词回退到脚本模式")
            return []

        client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        prompt = LEGEND_QUERY_EXPANSION_PROMPT.format(query=query)

        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你只负责为 CAD 图例查询生成检索关键词。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=128,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            data = json.loads(content)
            keywords = data.get("keywords", [])
            if not isinstance(keywords, list):
                return []
            normalized = []
            for item in keywords:
                if not isinstance(item, str):
                    continue
                text = re.sub(r"\s+", " ", item).strip()
                if len(text) >= 2:
                    normalized.append(text)
            return normalized[:8]
        except Exception as exc:
            logger.warning("图例查询扩词失败，回退到脚本模式: %s", exc)
            return []


class LegendPointReviewService:
    """图例单点复核服务，仅用于边界点的 keep/exclude 裁决。"""

    def __init__(
        self,
        api_key: str,
        model: str = "qwen-plus",
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    async def review(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from openai import AsyncOpenAI
        except ImportError:
            logger.warning("openai 依赖不可用，图例单点复核回退到脚本模式")
            return {"decision": "exclude", "confidence": 0.0, "reason": "LLM 不可用"}

        client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url, timeout=20, max_retries=0)
        prompt = LEGEND_POINT_REVIEW_PROMPT.format(
            payload=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        )

        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是谨慎的 CAD 图例复核助手，只输出 JSON。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=180,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            data = json.loads(content)
            decision = data.get("decision")
            if decision not in {"keep", "exclude"}:
                return {"decision": "exclude", "confidence": 0.0, "reason": "LLM 输出无效"}
            confidence = data.get("confidence", 0.0)
            try:
                confidence = float(confidence)
            except (TypeError, ValueError):
                confidence = 0.0
            reason = str(data.get("reason", "")).strip() or "LLM 未提供原因"
            return {
                "decision": decision,
                "confidence": max(0.0, min(1.0, confidence)),
                "reason": reason,
            }
        except Exception as exc:
            logger.warning("图例单点复核失败，回退到脚本模式: %s", exc)
            return {"decision": "exclude", "confidence": 0.0, "reason": f"LLM 调用失败: {exc}"}


def get_legend_query_expansion_service() -> Optional[LegendQueryExpansionService]:
    if not settings.LLM_ENABLED or not settings.QWEN_API_KEY:
        return None
    return LegendQueryExpansionService(
        api_key=settings.QWEN_API_KEY,
        model=settings.QWEN_MODEL,
        base_url=settings.QWEN_BASE_URL,
    )


def get_legend_point_review_service() -> Optional[LegendPointReviewService]:
    if not settings.LLM_ENABLED or not settings.QWEN_API_KEY:
        return None
    return LegendPointReviewService(
        api_key=settings.QWEN_API_KEY,
        model=settings.QWEN_MODEL,
        base_url=settings.QWEN_BASE_URL,
    )
