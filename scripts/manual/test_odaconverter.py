"""
使用 ODA File Converter 测试 DWG 转换
"""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.utils.dwg_converter import DWGConverter
from app.parsers.dxf_parser import DxfParser

async def test_conversion():
    """测试 DWG 转换"""
    print("=" * 80)
    print("使用 ODA File Converter 测试 DWG 转换")
    print("=" * 80)

    converter = DWGConverter()
    print(f"\n转换器: {converter.converter_type}")
    print(f"路径: {converter.converter_path}")

    files = [
        "/Users/fzzf/Desktop/20250701西农大教学楼建筑-自然排烟方案(1).dwg",
        "/Users/fzzf/Desktop/20250819西农大3#教学楼电气_t3(1).dwg",
        "/Users/fzzf/Desktop/西农大教学楼建筑_t3 - 给排水 - 3_t3(1).dwg",
    ]

    for dwg_path in files:
        print(f"\n{'='*60}")
        print(f"处理: {Path(dwg_path).name}")
        print('='*60)

        # 转换
        print("1. 转换 DWG 到 DXF...")
        success, dxf_path, error = converter.convert(dwg_path)

        if not success:
            print(f"   ❌ 转换失败: {error}")
            continue

        print(f"   ✅ 转换成功: {dxf_path}")

        # 解析
        print("2. 解析 DXF...")
        parser = DxfParser()

        try:
            result = parser.parse(dxf_path)
            print(f"   ✅ 解析成功")
            print(f"   - 图层: {len(result.layers)}")
            print(f"   - 图块: {len(result.blocks)}")
            print(f"   - 实体: {len(result.entities)}")
            print(f"   - 插入点: {len(result.inserts)}")

            # 提取门窗信息
            doors = []
            windows = []
            for name, block in result.blocks.items():
                if block.get('is_door_window'):
                    name_upper = name.upper()
                    if '门' in name_upper or name_upper.startswith('M'):
                        doors.append({
                            'name': name,
                            'count': block.get('insert_count', 0)
                        })
                    if '窗' in name_upper or name_upper.startswith('C'):
                        windows.append({
                            'name': name,
                            'count': block.get('insert_count', 0)
                        })

            if doors:
                total_doors = sum(d['count'] for d in doors)
                print(f"   - 门: {len(doors)}种, 共{total_doors}个")
                for d in doors[:3]:
                    print(f"      * {d['name']}: {d['count']}个")

            if windows:
                total_windows = sum(w['count'] for w in windows)
                print(f"   - 窗: {len(windows)}种, 共{total_windows}个")
                for w in windows[:3]:
                    print(f"      * {w['name']}: {w['count']}个")

        except Exception as e:
            print(f"   ❌ 解析失败: {e}")

if __name__ == "__main__":
    asyncio.run(test_conversion())
