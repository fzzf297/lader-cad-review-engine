"""
Pytest 配置和 fixtures
"""
import pytest
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))


@pytest.fixture
def sample_dxf_data():
    """示例 DXF 数据"""
    return {
        "file_info": {
            "dxf_version": "AC1032",
            "units": 6,
            "units_name": "米"
        },
        "layers": {
            "墙体": {"name": "墙体", "color": 1, "linetype": "Continuous", "off": False},
            "门窗": {"name": "门窗", "color": 2, "linetype": "Continuous", "off": False},
            "标注": {"name": "标注", "color": 3, "linetype": "Continuous", "off": False},
            "Layer1": {"name": "Layer1", "color": 7, "linetype": "Continuous", "off": False},
        },
        "blocks": {
            "M1021": {
                "name": "M1021",
                "entity_count": 10,
                "insert_count": 5,
                "is_door_window": True
            },
            "C1515": {
                "name": "C1515",
                "entity_count": 8,
                "insert_count": 3,
                "is_door_window": True
            },
            "COLUMN": {
                "name": "COLUMN",
                "entity_count": 5,
                "insert_count": 10,
                "is_door_window": False
            }
        },
        "entities": [
            {"type": "LINE", "layer": "墙体", "length": 100},
            {"type": "LINE", "layer": "墙体", "length": 200},
            {"type": "ARC", "layer": "门窗", "radius": 50},
            {"type": "TEXT", "layer": "标注", "content": "标注文字", "height": 3.5},
            {"type": "INSERT", "layer": "门窗", "name": "M1021"},
        ],
        "texts": [
            {"content": "标注文字1", "height": 3.5, "layer": "标注"},
            {"content": "标注文字2", "height": 2.0, "layer": "标注"},
        ],
        "dimensions": [
            {"text": "100", "style": "Standard", "layer": "标注"},
            {"text": "200", "style": "Standard", "layer": "标注"},
        ],
        "statistics": {
            "layer_count": 4,
            "block_count": 3,
            "entity_count": 5,
            "door_count": 5,
            "window_count": 3,
        }
    }


@pytest.fixture
def sample_contract_content():
    """示例合同内容"""
    return {
        "full_text": """
        建设工程施工合同

        甲方：XX房地产开发公司
        乙方：XX建筑工程公司

        一、工程概况
        本工程为XX住宅楼项目，位于XX市XX区。

        二、承包范围
        1. 门窗工程：铝合金门窗100套
        2. 管道工程：给排水管道500米
        3. 电气工程：开关插座200个

        三、合同价款
        本工程总价款为人民币500万元。
        """,
        "paragraphs": [
            "建设工程施工合同",
            "甲方：XX房地产开发公司",
            "乙方：XX建筑工程公司",
        ],
        "tables": [
            [
                ["序号", "项目名称", "数量", "单位", "单价"],
                ["1", "铝合金门M1021", "50", "套", "2000"],
                ["2", "铝合金窗C1515", "50", "套", "1500"],
                ["3", "给水管DN100", "300", "米", "80"],
                ["4", "排水管DN150", "200", "米", "100"],
            ]
        ],
        "metadata": {
            "file_type": "word",
            "paragraph_count": 20,
            "table_count": 1
        }
    }