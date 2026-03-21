#!/usr/bin/env python3
"""测试 DWG 转换器是否能找到本地 LibreDWG"""
import sys
import shutil
from pathlib import Path

# 计算项目本地 LibreDWG 路径
project_root = Path(__file__).parent.parent
libredwg_path = project_root / "tools" / "libredwg" / "install" / "bin" / "dwg2dxf"

print(f"项目根目录: {project_root}")
print(f"LibreDWG 路径: {libredwg_path}")
print(f"LibreDWG 存在: {libredwg_path.exists()}")

# 检查系统 PATH
system_dwg2dxf = shutil.which("dwg2dxf")
print(f"\n系统 PATH 中的 dwg2dxf: {system_dwg2dxf}")

# 检查转换器类型
if libredwg_path.exists():
    print("\n✅ 找到项目本地 LibreDWG！")
    print(f"   路径: {libredwg_path}")
    print(f"   类型: libredwg")
    print(f"   版本: ", end="")
    import subprocess
    result = subprocess.run([str(libredwg_path), "--version"], capture_output=True, text=True)
    print(result.stdout.strip() or result.stderr.strip())
    sys.exit(0)
elif system_dwg2dxf:
    print("\n✅ 找到系统 LibreDWG！")
    print(f"   路径: {system_dwg2dxf}")
    sys.exit(0)
else:
    print("\n❌ 未找到 LibreDWG")
    sys.exit(1)
