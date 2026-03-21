"""
测试合同解析功能
"""
import urllib.request
import urllib.parse
import json
import sys

BASE_URL = "http://localhost:8000"

def upload_contract():
    """上传合同文件"""
    print("=" * 60)
    print("步骤 1: 上传合同文件")
    print("=" * 60)

    file_path = "/tmp/contract.doc"

    # 构建 multipart 请求
    boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
    data = []
    data.append(f'--{boundary}'.encode())
    data.append(b'Content-Disposition: form-data; name="file"; filename="contract.doc"')
    data.append(b'Content-Type: application/msword')
    data.append(b'')
    with open(file_path, 'rb') as f:
        data.append(f.read())
    data.append(f'--{boundary}--'.encode())

    body = b'\r\n'.join(data)

    headers = {
        'Content-Type': f'multipart/form-data; boundary={boundary}',
        'Content-Length': str(len(body))
    }

    req = urllib.request.Request(f"{BASE_URL}/api/v1/upload", data=body, headers=headers, method='POST')

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode())
            print(f"✅ 上传成功")
            print(f"   文件ID: {data.get('file_id')}")
            print(f"   文件名: {data.get('filename')}")
            print(f"   文件类型: {data.get('file_type')}")
            return data.get('file_id')
    except urllib.error.HTTPError as e:
        print(f"❌ 上传失败: {e.code}")
        print(f"   响应: {e.read().decode()[:500]}")
        return None
    except Exception as e:
        print(f"❌ 上传失败: {e}")
        return None

def get_construction_scope(file_id):
    """获取施工范围（材料设备表）"""
    print("\n" + "=" * 60)
    print("步骤 2: 解析发包人供应材料设备一览表")
    print("=" * 60)

    url = f"{BASE_URL}/api/v1/parse/contract/{file_id}/construction-scope"
    print(f"请求: {url}")

    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            data = json.loads(response.read().decode())
            print(f"✅ 解析成功")
            print(f"\n📋 解析状态: {data.get('parse_status')}")

            material_list = data.get('material_supply_list', {})

            if material_list.get('table_found'):
                print(f"\n📄 表格名称: {material_list.get('table_name', 'N/A')}")
                print(f"🏗️  工程名称: {material_list.get('project_name', 'N/A')}")
                print(f"📍 施工地点: {material_list.get('location', 'N/A')}")

                items = material_list.get('items', [])
                print(f"\n📦 材料/设备清单 (共 {len(items)} 项):")
                print("-" * 80)
                print(f"{'序号':<6}{'名称':<20}{'规格型号':<20}{'单位':<8}{'数量':<10}{'备注':<10}")
                print("-" * 80)

                for item in items[:20]:  # 只显示前20项
                    print(f"{item.get('item_no', ''):<6}{item.get('name', '')[:18]:<20}{item.get('specification', '')[:18]:<20}{item.get('unit', ''):<8}{str(item.get('quantity', ''))[:8]:<10}{item.get('remarks', '')[:8]:<10}")

                if len(items) > 20:
                    print(f"\n... 还有 {len(items) - 20} 项 ...")

                # 汇总信息
                summary = material_list.get('summary', {})
                if summary:
                    print(f"\n📊 汇总:")
                    print(f"   总项数: {summary.get('total_items', 'N/A')}")
                    categories = summary.get('categories', {})
                    if categories:
                        print(f"   按分类:")
                        for cat, count in categories.items():
                            print(f"      - {cat}: {count}")
            else:
                print(f"\n⚠️  未找到'发包人供应材料设备一览表'")
                print(f"   返回数据: {json.dumps(material_list, ensure_ascii=False, indent=2)[:500]}")

            return data
    except urllib.error.HTTPError as e:
        print(f"❌ 解析失败: {e.code}")
        print(f"   响应: {e.read().decode()[:500]}")
        return None
    except Exception as e:
        print(f"❌ 解析失败: {e}")
        return None

def main():
    print("\n🔍 合同材料设备表解析测试\n")

    # 上传文件
    file_id = upload_contract()
    if not file_id:
        sys.exit(1)

    # 获取材料设备表
    result = get_construction_scope(file_id)

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    main()
