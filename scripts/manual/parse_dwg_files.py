"""
解析三个 DWG 图纸，提取统计信息用于与合同材料设备表对比
"""
import asyncio
import sys
import json
from pathlib import Path

# 添加 backend 到路径
backend_path = str(Path(__file__).parent.parent.parent / "backend")
sys.path.insert(0, backend_path)

print(f"Python path: {sys.path}")

from app.parsers.dxf_parser import DxfParser
from app.utils.dwg_converter import DWGConverter
from datetime import datetime

def parse_with_recover_mode(dxf_path: str):
    """使用恢复模式解析 DXF - 使用 ezdxf recover"""
    from datetime import datetime
    import ezdxf
    from ezdxf import recover

    result = type('Result', (), {})()

    try:
        # 使用 recover 模式读取损坏的 DXF
        doc, auditor = recover.readfile(dxf_path)
        print(f"   ✓ 使用 recover 模式读取成功")
    except Exception as e:
        print(f"   ❌ recover 模式也失败: {e}")
        return None

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
    insert_count = 0
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
                insert_count += 1
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
    """判断是否为门窗图块 - 只匹配标准命名"""
    import re
    if not name or not isinstance(name, str):
        return False

    name_upper = name.upper()

    # 标准门窗命名 M1021, C1515 等（严格匹配）
    if re.match(r'^[MC]\d{3,4}$', name_upper):
        return True

    # 排除常见非门窗图块
    exclude_patterns = ['*MODEL_SPACE', '*PAPER_SPACE', 'SHEET', '图框', 'LOGO', '底图']
    if any(p in name_upper for p in exclude_patterns):
        return False

    # 关键字匹配（更严格）
    # 门：以 M 开头且后跟数字，或包含 DOOR/门
    if re.match(r'^M\d+', name_upper) or 'DOOR' in name_upper:
        return True

    # 窗：以 C 开头且后跟数字，或包含 WINDOW/窗（但不是窗帘）
    if re.match(r'^C\d+', name_upper):
        return True
    if 'WINDOW' in name_upper:
        return True
    if '窗' in name and '窗帘' not in name and '门窗' not in name:
        return True

    return False


def parse_dwg_file(file_path: str) -> dict:
    """解析单个 DWG 文件（同步版本）"""
    print(f"\n{'='*60}")
    print(f"解析文件: {Path(file_path).name}")
    print('='*60)

    # 1. 转换 DWG 到 DXF
    converter = DWGConverter()
    success, dxf_path, error = converter.convert(file_path)

    if not success:
        print(f"❌ 转换失败: {error}")
        return None

    print(f"✓ 转换成功: {dxf_path}")

    # 2. 解析 DXF - 使用 recover 模式
    parser = DxfParser()
    try:
        result = parser.parse(dxf_path)
    except Exception as e:
        print(f"⚠️ 标准解析失败，尝试使用恢复模式...")
        try:
            # 使用 recover 模式读取损坏的 DXF
            result = parse_with_recover_mode(dxf_path)
            if result is None:
                return None
        except Exception as e2:
            print(f"❌ DXF 解析失败: {e2}")
            return None

    # 3. 提取统计信息
    stats = {
        "filename": Path(file_path).name,
        "dxf_version": result.file_info.get("dxf_version", ""),
        "units": result.file_info.get("units_name", ""),
        "layers_count": len(result.layers),
        "blocks_count": len(result.blocks),
        "entities_count": len(result.entities),
        "inserts_count": len(result.inserts),
    }

    # 4. 分类统计图块
    blocks_by_category = {
        "门窗": [],
        "管道": [],
        "电气": [],
        "消防": [],
        "土建": [],
        "装修": [],
        "其他": []
    }

    for name, block in result.blocks.items():
        category = categorize_block(name)
        blocks_by_category[category].append({
            "name": name,
            "count": block.get("insert_count", 0),
            "is_door_window": block.get("is_door_window", False)
        })

    # 5. 门窗详情
    doors = []
    windows = []
    for name, block in result.blocks.items():
        if block.get("is_door_window"):
            name_upper = name.upper()
            insert_count = block.get("insert_count", 0)

            # 解析规格
            spec = parse_spec(name)

            item = {
                "name": name,
                "count": insert_count,
                "specification": spec
            }

            if any(kw in name_upper for kw in ["门", "DOOR", "M"]):
                if name_upper.startswith('M') and len(name_upper) >= 3:
                    doors.append(item)
                elif "门" in name_upper or "DOOR" in name_upper:
                    doors.append(item)

            if any(kw in name_upper for kw in ["窗", "WINDOW", "C"]):
                if name_upper.startswith('C') and len(name_upper) >= 3:
                    windows.append(item)
                elif "窗" in name_upper or "WINDOW" in name_upper:
                    windows.append(item)

    # 6. 提取文字内容（可能包含设备名称）
    texts = []
    for text in result.texts[:20]:  # 只取前20个
        content = text.get("content", "").strip()
        if content and len(content) > 2:
            texts.append(content[:50])

    stats["blocks_by_category"] = blocks_by_category
    stats["doors"] = doors
    stats["windows"] = windows
    stats["total_doors"] = sum(d["count"] for d in doors)
    stats["total_windows"] = sum(w["count"] for w in windows)
    stats["text_samples"] = texts

    return stats

def categorize_block(block_name: str) -> str:
    """根据图块名称判断分类"""
    import re
    name_upper = block_upper = block_name.upper()

    # 门窗
    if any(kw in name_upper for kw in ["门", "窗", "DOOR", "WINDOW", "M", "C"]):
        if re.match(r'^[MC]\d{2,4}$', name_upper):
            return "门窗"
        if any(kw in name_upper for kw in ["门", "DOOR", "M"]):
            return "门窗"
        if any(kw in name_upper for kw in ["窗", "WINDOW", "C"]):
            return "门窗"

    # 消防
    if any(kw in name_upper for kw in ["消防", "FIRE", "烟感", "喷淋", "消火栓", "FIREHYDRANT", "SPRINKLER"]):
        return "消防"

    # 管道
    if any(kw in name_upper for kw in ["管", "PIPE", "DUCT", "水", "风", "VALVE", "阀门"]):
        return "管道"

    # 电气
    if any(kw in name_upper for kw in ["电", "开关", "插座", "灯具", "ELEC", "SWITCH", "SOCKET", "LIGHT"]):
        return "电气"

    # 土建
    if any(kw in name_upper for kw in ["柱", "梁", "板", "墙", "COLUMN", "BEAM", "SLAB", "WALL"]):
        return "土建"

    # 装修
    if any(kw in name_upper for kw in ["吊顶", "地面", "墙裙", "CEILING", "FLOOR"]):
        return "装修"

    return "其他"

def parse_spec(block_name: str) -> str:
    """从图块名称解析规格"""
    import re
    match = re.match(r'^[MC](\d{2})(\d{2,3})$', block_name.upper())
    if match:
        width = int(match.group(1)) * 10
        height = int(match.group(2)) * 10 if len(match.group(2)) == 2 else int(match.group(2))
        return f"{width}x{height}mm"
    return ""

def main():
    files = [
        "/Users/fzzf/Desktop/20250701西农大教学楼建筑-自然排烟方案(1).dwg",
        "/Users/fzzf/Desktop/20250819西农大3#教学楼电气_t3(1).dwg",
        "/Users/fzzf/Desktop/西农大教学楼建筑_t3 - 给排水 - 3_t3(1).dwg",
    ]

    all_results = []

    for file_path in files:
        try:
            result = parse_dwg_file(file_path)
            if result:
                all_results.append(result)
        except Exception as e:
            print(f"❌ 解析失败 {file_path}: {e}")
            import traceback
            traceback.print_exc()

    # 输出汇总
    print("\n" + "="*60)
    print("汇总统计")
    print("="*60)

    for result in all_results:
        print(f"\n📁 {result['filename']}")
        print(f"   图层: {result['layers_count']}, 图块: {result['blocks_count']}, 实体: {result['entities_count']}")

        # 分类统计
        print("   分类统计:")
        for category, items in result['blocks_by_category'].items():
            if items:
                total = sum(item['count'] for item in items)
                print(f"     - {category}: {len(items)}种图块, 共{total}个")

        # 门窗统计
        if result['doors']:
            print(f"   🚪 门: {result['total_doors']}个")
            for door in result['doors'][:5]:
                print(f"      - {door['name']}: {door['count']}个 ({door['specification']})")
            if len(result['doors']) > 5:
                print(f"      ... 还有 {len(result['doors'])-5} 种门")

        if result['windows']:
            print(f"   🪟 窗: {result['total_windows']}个")
            for window in result['windows'][:5]:
                print(f"      - {window['name']}: {window['count']}个 ({window['specification']})")
            if len(result['windows']) > 5:
                print(f"      ... 还有 {len(result['windows'])-5} 种窗")

    # 保存详细结果到文件
    output_path = Path("/tmp/dwg_parse_results.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n✓ 详细结果已保存到: {output_path}")

if __name__ == "__main__":
    main()
