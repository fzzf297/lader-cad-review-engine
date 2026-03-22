"""
分析三个 DWG 图纸与合同的匹配情况
"""
import json
from pathlib import Path

def load_results():
    """加载解析结果"""
    with open('/tmp/dwg_parse_results.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def analyze_matching():
    """分析匹配情况"""
    results = load_results()

    print("=" * 80)
    print("DWG 图纸解析与合同匹配分析报告")
    print("=" * 80)

    # 1. 解析概况
    print("\n📊 解析概况")
    print("-" * 80)

    files_status = [
        ("20250701西农大教学楼建筑-自然排烟方案(1).dwg", "❌ 解析失败", "DXF结构错误"),
        ("20250819西农大3#教学楼电气_t3(1).dwg", "❌ 解析失败", "编码问题"),
        ("西农大教学楼建筑_t3 - 给排水 - 3_t3(1).dwg", "✅ 解析成功", "130图层, 1173图块"),
    ]

    for filename, status, note in files_status:
        print(f"  {filename}")
        print(f"    状态: {status} ({note})")

    # 2. 成功解析的文件详情
    print("\n📋 给排水图纸详情")
    print("-" * 80)

    if results:
        result = results[0]
        print(f"  图层数量: {result['layers_count']}")
        print(f"  图块数量: {result['blocks_count']}")
        print(f"  实体数量: {result['entities_count']}")
        print(f"  插入点数量: {result['inserts_count']}")

        # 分类统计
        print(f"\n  分类统计:")
        for category, items in result['blocks_by_category'].items():
            if items and category != '其他':
                # 过滤掉 count=0 的
                valid_items = [i for i in items if i['count'] > 0]
                if valid_items:
                    print(f"    {category}: {len(valid_items)} 种有引用的图块")

    # 3. 合同材料设备表预期内容（示例）
    print("\n📄 合同材料设备表预期内容")
    print("-" * 80)

    # 根据用户提供的合同文件名，这是一个消防相关的合同
    expected_items = [
        "消防栓",
        "消防喷淋",
        "烟感探测器",
        "消防管道",
        "消防阀门",
        "电气线路",
        "配电箱",
        "排烟设备",
    ]

    print("  根据合同名称【北校区3#教学楼消防设施更新改造】，预期材料设备包括:")
    for item in expected_items:
        print(f"    - {item}")

    # 4. 匹配分析
    print("\n🔍 匹配分析")
    print("-" * 80)

    print("  当前解析结果与合同材料的匹配情况:")
    print()
    print("  问题 1: 图纸解析覆盖率")
    print("    - 3个文件中只有1个成功解析 (33%)")
    print("    - 自然排烟方案和电气文件因编码/结构问题无法解析")
    print()
    print("  问题 2: 图块引用统计缺失")
    print("    - 成功解析的给排水文件没有统计到图块引用数量")
    print("    - 无法确认图纸中实际有多少个阀门/管道")
    print()
    print("  问题 3: 分类准确性")
    print("    - 当前门窗判断逻辑过于宽松，需要优化")
    print("    - 缺少消防设备专用分类")
    print()
    print("  问题 4: 合同-图纸关联")
    print("    - 合同中的'发包人供应材料设备一览表'需要提取具体清单")
    print("    - 需要将清单中的设备与图纸中的图块进行匹配")

    # 5. 建议
    print("\n💡 改进建议")
    print("-" * 80)
    print("""
  1. 优化 DWG 解析:
     - 优先直接获取稳定 DXF 输入
     - 处理中文编码问题
     - 增加 DXF 损坏文件的恢复能力

  2. 完善合同解析:
     - 提取合同中的'发包人供应材料设备一览表'
     - 建立材料设备分类体系（消防、电气、管道等）

  3. 改进匹配逻辑:
     - 建立材料名称与图块名称的映射关系
     - 例如: "消防栓" -> ["消火栓", "FIRE HYDRANT", "HXX"]
     - 支持规格型号匹配（如 DN100, 双栓等）

  4. 验证流程:
     - 对比合同数量 vs 图纸数量
     - 标记缺失项和多余项
     - 生成匹配报告
    """)

    # 6. 当前能做的对比
    print("\n📊 当前可行的对比（基于给排水图纸）")
    print("-" * 80)

    if results:
        result = results[0]
        # 查找可能相关的图块
        valve_blocks = [b for b in result['blocks_by_category'].get('管道', [])
                        if 'VALVE' in b['name'].upper()]
        print(f"  图纸中找到的阀门图块: {len(valve_blocks)} 种")
        for vb in valve_blocks[:5]:
            print(f"    - {vb['name']}")

if __name__ == "__main__":
    analyze_matching()
