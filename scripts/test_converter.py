#!/usr/bin/env python3
"""测试系统环境中是否可用 DWG 转换器"""
import shutil

# 检查系统 PATH
system_dwg2dxf = shutil.which("dwg2dxf")
system_oda = shutil.which("ODAFileConverter")

print(f"系统 PATH 中的 dwg2dxf: {system_dwg2dxf}")
print(f"系统 PATH 中的 ODAFileConverter: {system_oda}")

# 检查转换器类型
if system_oda:
    print("\n✅ 找到系统 ODA File Converter")
    print(f"   路径: {system_oda}")
elif system_dwg2dxf:
    print("\n✅ 找到系统 LibreDWG！")
    print(f"   路径: {system_dwg2dxf}")
else:
    print("\n❌ 未找到系统 DWG 转换器")
    print("   请安装 ODA File Converter 或 LibreDWG")
