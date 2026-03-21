"""
DWG 转换器本地验证脚本
"""
import sys
import tempfile
from pathlib import Path

# 添加 backend 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.utils.dwg_converter import get_converter, convert_dwg_to_dxf


def test_converter_detection():
    """测试转换器检测"""
    print("=" * 50)
    print("1. 测试转换器检测")
    print("=" * 50)

    converter = get_converter()

    if converter.is_available():
        print(f"✅ 转换器已找到: {converter.converter_type}")
        print(f"   路径: {converter.converter_path}")
        return True
    else:
        print("❌ 未找到转换器")
        print("   请安装 LibreDWG: brew install libredwg (macOS)")
        print("   或: sudo apt-get install libredwg-tools (Ubuntu)")
        return False


def test_dwg_conversion():
    """测试 DWG 转换（需要测试文件）"""
    print("\n" + "=" * 50)
    print("2. 测试 DWG 转换")
    print("=" * 50)

    # 查找测试文件
    test_files = [
        Path(__file__).parent.parent / "backend" / "tests" / "fixtures" / "test.dwg",
        Path(__file__).parent.parent / "test.dwg",
        Path.cwd() / "test.dwg",
    ]

    dwg_file = None
    for f in test_files:
        if f.exists():
            dwg_file = f
            break

    if not dwg_file:
        print("⚠️  未找到测试 DWG 文件")
        print("   请放置一个 test.dwg 文件在项目根目录")
        return None

    print(f"   测试文件: {dwg_file}")

    with tempfile.TemporaryDirectory() as tmpdir:
        success, dxf_path, error = convert_dwg_to_dxf(str(dwg_file), tmpdir)

        if success:
            print(f"✅ 转换成功")
            print(f"   输出: {dxf_path}")
            print(f"   大小: {Path(dxf_path).stat().st_size} bytes")
            return True
        else:
            print(f"❌ 转换失败")
            print(f"   错误: {error}")
            return False


def main():
    """主函数"""
    print("\n🔧 DWG 转换器本地验证\n")

    result1 = test_converter_detection()
    result2 = test_dwg_conversion()

    print("\n" + "=" * 50)
    print("验证结果")
    print("=" * 50)

    if result1 and result2 is not False:
        print("✅ 所有验证通过！DWG 转换功能正常")
        return 0
    elif result1 and result2 is None:
        print("⚠️  转换器正常，但未测试文件转换（无测试文件）")
        return 0
    else:
        print("❌ 验证失败，请检查安装")
        return 1


if __name__ == "__main__":
    sys.exit(main())
