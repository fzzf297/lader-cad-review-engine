"""
使用 ODA File Converter 测试 DWG 转换 (带 recover 模式)
"""
import sys
import asyncio
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.utils.dwg_converter import DWGConverter

def extract_basic_info(doc, dxf_path: str):
    """使用 recover 模式提取基本信息"""
    result = type('Result', (), {})()

    # 文件信息
    result.file_info = {
        "filename": Path(dxf_path).name,
        "dxf_version": str(doc.dxfversion) if hasattr(doc, 'dxfversion') else "unknown",
        "units": 0,
        "units_name": "unknown"
    }

    # 提取图层
    result.layers = {}
    if hasattr(doc, 'layers'):
        for layer in doc.layers:
            try:
                name = layer.dxf.name
                result.layers[name] = {
                    "name": name,
                    "color": layer.dxf.color,
                    "linetype": layer.dxf.linetype,
                }
            except:
                pass

    # 提取图块
    result.blocks = {}
    result.inserts = []

    if hasattr(doc, 'blocks'):
        for block in doc.blocks:
            try:
                name = block.name
                result.blocks[name] = {
                    "name": name,
                    "entity_count": len(block),
                    "insert_count": 0,
                    "is_door_window": is_door_window_block(name)
                }
            except:
                pass

    # 提取插入点
    msp = doc.modelspace()
    for entity in msp:
        try:
            if entity.dxftype() == 'INSERT':
                name = entity.dxf.name
                result.inserts.append({
                    "name": name,
                    "insert": {
                        "x": entity.dxf.insert.x,
                        "y": entity.dxf.insert.y,
                        "z": entity.dxf.insert.z,
                    }
                })
                # 更新图块引用计数
                if name in result.blocks:
                    result.blocks[name]["insert_count"] += 1
        except:
            pass

    # 实体和文本
    result.entities = []
    result.texts = []

    for entity in msp:
        try:
            etype = entity.dxftype()
            result.entities.append({"type": etype})

            if etype in ['TEXT', 'MTEXT']:
                content = ""
                if etype == 'MTEXT' and hasattr(entity, 'text'):
                    content = entity.text
                elif hasattr(entity.dxf, 'text'):
                    content = entity.dxf.text

                if content:
                    result.texts.append({
                        "type": etype,
                        "content": content,
                        "layer": entity.dxf.layer
                    })
        except:
            pass

    # 解析元数据
    result.parse_metadata = {
        "parsed_at": datetime.now().isoformat(),
        "parse_duration_seconds": 0,
        "file_path": dxf_path,
        "parser_version": "recover_mode"
    }

    return result

def is_door_window_block(name: str) -> bool:
    """判断是否为门窗图块"""
    import re
    if not name or not isinstance(name, str):
        return False

    name_upper = name.upper()

    # 标准门窗命名 M1021, C1515 等
    if re.match(r'^[MC]\d{3,4}$', name_upper):
        return True

    # 排除常见非门窗图块
    exclude_patterns = ['*MODEL_SPACE', '*PAPER_SPACE', 'SHEET', '图框', 'LOGO', '底图']
    if any(p in name_upper for p in exclude_patterns):
        return False

    # 关键字匹配
    if re.match(r'^M\d+', name_upper) or 'DOOR' in name_upper:
        return True
    if re.match(r'^C\d+', name_upper):
        return True
    if 'WINDOW' in name_upper:
        return True

    return False

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

    all_results = []

    for dwg_path in files:
        print(f"\n{'='*60}")
        print(f"处理: {Path(dwg_path).name}")
        print('='*60)

        # 转换
        print("1. 转换 DWG 到 DXF...")
        success, dxf_path, error = converter.convert(dwg_path)

        if not success:
            print(f"   转换失败: {error}")
            continue

        print(f"   转换成功: {dxf_path}")

        # 解析
        print("2. 解析 DXF...")

        try:
            from app.parsers.dxf_parser import DxfParser
            parser = DxfParser()
            result = parser.parse(dxf_path)
            print(f"   标准解析成功")
        except Exception as e:
            print(f"   标准解析失败，尝试 recover 模式...")
            try:
                from ezdxf import recover
                doc, auditor = recover.readfile(dxf_path)
                result = extract_basic_info(doc, dxf_path)
                print(f"   recover 模式成功")
            except Exception as e2:
                print(f"   解析失败: {e2}")
                continue

        print(f"   - 图层: {len(result.layers)}")
        print(f"   - 图块: {len(result.blocks)}")
        print(f"   - 插入点: {len(result.inserts)}")

        # 统计图块引用
        blocks_with_inserts = [(name, b) for name, b in result.blocks.items() if b.get('insert_count', 0) > 0]
        print(f"   - 有引用的图块: {len(blocks_with_inserts)}")

        # 提取消防相关图块
        fire_keywords = ['消防', '消火栓', '阀门', 'VALVE', '烟感', '探测器', '报警', 'FIRE']
        fire_blocks = []
        for name, block in result.blocks.items():
            if any(kw in name.upper() for kw in fire_keywords):
                fire_blocks.append({
                    'name': name,
                    'count': block.get('insert_count', 0)
                })

        if fire_blocks:
            total_fire = sum(b['count'] for b in fire_blocks)
            print(f"   - 消防相关图块: {len(fire_blocks)}种, 共{total_fire}个")
            for b in fire_blocks[:5]:
                print(f"      * {b['name']}: {b['count']}个")

        # 保存结果
        all_results.append({
            'filename': Path(dwg_path).name,
            'layers': len(result.layers),
            'blocks': len(result.blocks),
            'inserts': len(result.inserts),
            'fire_blocks': fire_blocks
        })

    # 汇总
    print("\n" + "="*60)
    print("汇总")
    print("="*60)
    for r in all_results:
        print(f"\n{r['filename']}:")
        print(f"  图层: {r['layers']}, 图块: {r['blocks']}, 插入点: {r['inserts']}")
        if r['fire_blocks']:
            total = sum(b['count'] for b in r['fire_blocks'])
            print(f"  消防设备: {len(r['fire_blocks'])}种, 共{total}个")

if __name__ == "__main__":
    asyncio.run(test_conversion())
