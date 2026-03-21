"""
直接测试 LLM API
"""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.core.config import settings

async def test_llm():
    """直接测试 LLM"""
    print("=" * 80)
    print("直接测试 LLM API")
    print("=" * 80)

    # 读取表格部分内容
    with open('/tmp/table_section.txt', 'r', encoding='utf-8') as f:
        table_section = f.read()

    print(f"表格部分内容长度: {len(table_section)} 字符")
    print(f"\n前500字符预览:")
    print(table_section[:500])

    # 调用 LLM
    try:
        from openai import AsyncOpenAI
    except ImportError:
        print("请安装 openai: pip install openai")
        return

    client = AsyncOpenAI(
        api_key=settings.QWEN_API_KEY,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )

    prompt = f"""
请从以下合同内容中提取"发包人供应材料设备一览表"中的所有材料设备信息。

合同内容：
{table_section}

请按以下 JSON 格式输出：
{{
  "table_found": true/false,
  "items": [
    {{
      "item_no": "序号",
      "name": "名称",
      "specification": "规格型号",
      "unit": "单位",
      "quantity": "数量",
      "remarks": "品牌/备注"
    }}
  ]
}}

注意：
1. 表格中包含33项材料设备，请全部提取
2. 规格型号要包含完整的技术参数
3. 如果找到表格，table_found 必须为 true
"""

    print(f"\n正在调用 LLM...")

    try:
        response = await client.chat.completions.create(
            model=settings.QWEN_MODEL,
            messages=[
                {"role": "system", "content": "你是一位专业的建筑合同分析专家，擅长提取材料设备清单。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=4096
        )

        content = response.choices[0].message.content
        print(f"\n✅ LLM 响应:")
        print(content[:3000])

        # 尝试解析 JSON
        import json
        import re

        # 提取 JSON 部分
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                print(f"\n📊 解析结果:")
                print(f"   table_found: {data.get('table_found')}")
                items = data.get('items', [])
                print(f"   提取到 {len(items)} 项材料设备")

                if items:
                    print(f"\n   前5项预览:")
                    for item in items[:5]:
                        print(f"      {item.get('item_no', 'N/A')}. {item.get('name', 'N/A')} - {item.get('quantity', 'N/A')}{item.get('unit', 'N/A')}")
            except json.JSONDecodeError as e:
                print(f"JSON 解析失败: {e}")

    except Exception as e:
        print(f"❌ LLM 调用失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_llm())
