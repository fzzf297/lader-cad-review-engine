"""
直接调用后端代码测试合同解析
"""
import sys
import asyncio
from pathlib import Path

# 添加 backend 到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.parsers.contract_parser import ContractParser
from app.services.review_service import ContractAnalysisService
from app.core.config import settings

async def test_contract_parsing():
    """测试合同解析"""
    print("=" * 80)
    print("直接调用后端代码测试合同解析")
    print("=" * 80)

    # 读取 txt 格式的合同文本
    contract_path = "/tmp/contract.txt"

    print("\n步骤 1: 读取合同文本")
    print("-" * 80)

    with open(contract_path, 'r', encoding='utf-8') as f:
        full_text = f.read()

    print(f"✅ 合同读取成功")
    print(f"   文本长度: {len(full_text)} 字符")

    # 创建 ContractContent 对象
    from app.parsers.contract_parser import ContractContent
    contract_content = ContractContent(
        full_text=full_text,
        paragraphs=full_text.split('\n'),
        tables=[]
    )

    # 2. 检查是否启用了 LLM
    print("\n步骤 2: 检查 LLM 配置")
    print("-" * 80)

    if not settings.LLM_ENABLED or not settings.QWEN_API_KEY:
        print(f"❌ LLM 未启用")
        print(f"   LLM_ENABLED: {settings.LLM_ENABLED}")
        print(f"   QWEN_API_KEY: {'已设置' if settings.QWEN_API_KEY else '未设置'}")
        print(f"\n   将使用备用方案：查看原始表格数据")

        # 显示表格内容
        if contract_content.tables:
            print(f"\n   发现 {len(contract_content.tables)} 个表格:")
            for i, table in enumerate(contract_content.tables[:3]):
                print(f"\n   表格 {i+1} ({len(table)} 行):")
                for j, row in enumerate(table[:5]):  # 只显示前5行
                    print(f"      行{j+1}: {row}")
                if len(table) > 5:
                    print(f"      ... 还有 {len(table)-5} 行 ...")
        else:
            print(f"   未发现表格")

        return

    # 3. 使用 LLM 分析材料设备表
    print("\n步骤 3: LLM 分析材料设备表")
    print("-" * 80)

    print(f"   使用模型: {settings.QWEN_MODEL}")
    print(f"   正在调用 API 分析... (可能需要 10-30 秒)")

    analyzer = ContractAnalysisService(
        api_key=settings.QWEN_API_KEY,
        model=settings.QWEN_MODEL
    )

    try:
        # 先测试截取逻辑
        print(f"\n   测试截取逻辑...")
        table_section = analyzer._extract_material_supply_section(contract_content.full_text)
        print(f"   截取内容长度: {len(table_section)} 字符")
        print(f"   前500字符: {table_section[:500]}")

        result = await analyzer.analyze_material_supply_list(contract_content)

        print(f"\n✅ LLM 分析完成")
        print(f"\n原始返回（前2000字符）:")
        import json
        print(json.dumps(result, ensure_ascii=False, indent=2)[:2000])

        if result.get('table_found'):
            print(f"\n📄 找到表格: {result.get('table_name', 'N/A')}")
            print(f"🏗️  工程名称: {result.get('project_name', 'N/A')}")
            print(f"📍 施工地点: {result.get('location', 'N/A')}")

            items = result.get('items', [])
            print(f"\n📦 材料/设备清单 (共 {len(items)} 项):")
            print("-" * 80)
            print(f"{'序号':<6}{'名称':<25}{'规格型号':<20}{'单位':<8}{'数量':<10}")
            print("-" * 80)

            for item in items[:30]:  # 显示前30项
                name = item.get('name', '')[:23]
                spec = item.get('specification', '')[:18]
                unit = item.get('unit', '')[:6]
                qty = str(item.get('quantity', ''))[:8]
                no = item.get('item_no', '')[:4]
                print(f"{no:<6}{name:<25}{spec:<20}{unit:<8}{qty:<10}")

            if len(items) > 30:
                print(f"\n... 还有 {len(items) - 30} 项 ...")

            # 汇总
            summary = result.get('summary', {})
            if summary:
                print(f"\n📊 汇总: 共 {summary.get('total_items', len(items))} 项")
                categories = summary.get('categories', {})
                if categories:
                    print(f"   分类统计:")
                    for cat, count in categories.items():
                        print(f"      - {cat}: {count} 项")
        else:
            print(f"\n⚠️  未找到'发包人供应材料设备一览表'")
            print(f"   返回结果:")
            import json
            print(f"   {json.dumps(result, ensure_ascii=False, indent=2)[:1000]}")

    except Exception as e:
        print(f"\n❌ LLM 分析失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_contract_parsing())
