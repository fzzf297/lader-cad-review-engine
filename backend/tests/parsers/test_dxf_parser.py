"""
DXF 解析器测试
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from app.parsers.dxf_parser import DxfParser, DxfParseResult, EntityExtractor


class TestEntityExtractor:
    """实体提取器测试"""

    def setup_method(self):
        self.extractor = EntityExtractor()

    def test_extract_line(self):
        """测试提取直线"""
        entity = Mock()
        entity.dxftype.return_value = "LINE"
        entity.dxf.start = Mock(x=0, y=0, z=0)
        entity.dxf.end = Mock(x=100, y=0, z=0)
        entity.dxf.linetype = "Continuous"
        entity.dxf.color = 1
        entity.dxf.layer = "墙体"
        entity.dxf.handle = "ABC123"

        result = self.extractor.extract(entity)

        assert result is not None
        assert result["type"] == "LINE"
        assert result["layer"] == "墙体"
        assert result["length"] == 100

    def test_extract_circle(self):
        """测试提取圆"""
        entity = Mock()
        entity.dxftype.return_value = "CIRCLE"
        entity.dxf.center = Mock(x=0, y=0, z=0)
        entity.dxf.radius = 50
        entity.dxf.layer = "轴线"
        entity.dxf.handle = "DEF456"

        result = self.extractor.extract(entity)

        assert result is not None
        assert result["type"] == "CIRCLE"
        assert result["radius"] == 50
        assert result["area"] == pytest.approx(7853.98, rel=0.01)

    def test_extract_arc(self):
        """测试提取圆弧"""
        entity = Mock()
        entity.dxftype.return_value = "ARC"
        entity.dxf.center = Mock(x=0, y=0, z=0)
        entity.dxf.radius = 100
        entity.dxf.start_angle = 0
        entity.dxf.end_angle = 90
        entity.dxf.layer = "门窗"
        entity.dxf.handle = "GHI789"

        result = self.extractor.extract(entity)

        assert result is not None
        assert result["type"] == "ARC"
        assert result["radius"] == 100

    def test_extract_text(self):
        """测试提取文字"""
        entity = Mock()
        entity.dxftype.return_value = "TEXT"
        entity.dxf.text = "标注文字"
        entity.dxf.insert = Mock(x=0, y=0, z=0)
        entity.dxf.height = 3.5
        entity.dxf.rotation = 0
        entity.dxf.style = "Standard"
        entity.dxf.layer = "标注"
        entity.dxf.handle = "TXT001"

        result = self.extractor.extract(entity)

        assert result is not None
        assert result["type"] == "TEXT"
        assert result["content"] == "标注文字"
        assert result["height"] == 3.5

    def test_extract_spline_accepts_array_like_points(self):
        """测试样条曲线兼容 numpy 数组风格控制点"""
        entity = Mock()
        entity.dxftype.return_value = "SPLINE"
        entity.control_points = [(1, 2, 3), [4, 5, 6]]
        entity.dxf.degree = 3
        entity.closed = False
        entity.dxf.layer = "曲线"
        entity.dxf.handle = "SPL001"

        result = self.extractor.extract(entity)

        assert result is not None
        assert result["type"] == "SPLINE"
        assert result["control_points"] == [
            {"x": 1.0, "y": 2.0, "z": 3.0},
            {"x": 4.0, "y": 5.0, "z": 6.0},
        ]
        assert result["degree"] == 3

    def test_extract_insert_with_attribs(self):
        """测试提取图块引用（带属性）"""
        entity = Mock()
        entity.dxftype.return_value = "INSERT"
        entity.dxf.name = "M1021"
        entity.dxf.insert = Mock(x=100, y=200, z=0)
        entity.dxf.xscale = 1
        entity.dxf.yscale = 1
        entity.dxf.zscale = 1
        entity.dxf.rotation = 0
        entity.dxf.layer = "门窗"
        entity.dxf.handle = "INS001"

        # 模拟属性
        attr1 = Mock()
        attr1.dxf.tag = "WIDTH"
        attr1.dxf.text = "1000"
        attr2 = Mock()
        attr2.dxf.tag = "HEIGHT"
        attr2.dxf.text = "2100"
        entity.attribs = [attr1, attr2]

        result = self.extractor.extract(entity)

        assert result is not None
        assert result["type"] == "INSERT"
        assert result["name"] == "M1021"
        assert result["attribs"]["WIDTH"] == "1000"
        assert result["attribs"]["HEIGHT"] == "2100"

    def test_extract_unsupported_entity(self):
        """测试不支持的实体类型"""
        entity = Mock()
        entity.dxftype.return_value = "UNSUPPORTED_TYPE"
        entity.dxf.layer = "0"
        entity.dxf.handle = "XXX"

        result = self.extractor.extract(entity)

        assert result is None


class TestDxfParser:
    """DXF 解析器测试"""

    def setup_method(self):
        self.parser = DxfParser()

    def test_is_door_window_block_door(self):
        """测试识别门图块"""
        assert self.parser._is_door_window_block("M1021") is True
        assert self.parser._is_door_window_block("door_entrance") is True
        assert self.parser._is_door_window_block("门") is True

    def test_is_door_window_block_window(self):
        """测试识别窗图块"""
        assert self.parser._is_door_window_block("C1515") is True
        assert self.parser._is_door_window_block("WINDOW_01") is True
        assert self.parser._is_door_window_block("窗") is True

    def test_is_door_window_block_not_door_window(self):
        """测试非门窗图块"""
        assert self.parser._is_door_window_block("COLUMN") is False
        assert self.parser._is_door_window_block("BEAM") is False
        assert self.parser._is_door_window_block("TABLE") is False

    @patch('app.parsers.dxf_parser.ezdxf.readfile')
    def test_parse_file_success(self, mock_readfile, sample_dxf_data):
        """测试成功解析 DXF 文件"""
        # 模拟 DXF 文档
        mock_doc = MagicMock()
        mock_doc.dxfversion = "AC1032"
        mock_doc.units = 6
        mock_doc.filename = "test.dxf"
        mock_doc.header.get = lambda key, default=None: default

        # 模拟图层
        mock_layer = MagicMock()
        mock_layer.dxf.name = "墙体"
        mock_layer.dxf.color = 1
        mock_layer.dxf.linetype = "Continuous"
        mock_layer.is_off.return_value = False
        mock_layer.is_frozen.return_value = False
        mock_layer.is_locked.return_value = False
        mock_layer.dxf.plot = 1
        mock_doc.layers = [mock_layer]

        # 模拟模型空间
        mock_msp = MagicMock()
        mock_msp.__iter__ = lambda self: iter([])
        mock_doc.modelspace.return_value = mock_msp

        # 模拟块
        mock_doc.blocks = []

        mock_readfile.return_value = mock_doc

        result = self.parser.parse("test.dxf")

        assert result is not None
        assert isinstance(result, DxfParseResult)
        assert result.file_info["dxf_version"] == "AC1032"

    def test_calculate_statistics(self, sample_dxf_data):
        """测试统计计算"""
        result = DxfParseResult(
            layers=sample_dxf_data["layers"],
            blocks=sample_dxf_data["blocks"],
            entities=sample_dxf_data["entities"],
            texts=sample_dxf_data["texts"],
            dimensions=sample_dxf_data["dimensions"],
        )

        stats = self.parser._calculate_statistics(result)

        assert stats["layer_count"] == 4
        assert stats["block_count"] == 3
        assert stats["entity_count"] == 5
        assert stats["text_count"] == 2
        assert stats["dimension_count"] == 2


class TestDxfParseResult:
    """解析结果数据类测试"""

    def test_default_values(self):
        """测试默认值"""
        result = DxfParseResult()

        assert result.file_info == {}
        assert result.layers == {}
        assert result.blocks == {}
        assert result.entities == []
        assert result.errors == []

    def test_custom_values(self):
        """测试自定义值"""
        result = DxfParseResult(
            file_info={"dxf_version": "AC1032"},
            layers={"墙体": {}},
            entities=[{"type": "LINE"}]
        )

        assert result.file_info["dxf_version"] == "AC1032"
        assert len(result.layers) == 1
        assert len(result.entities) == 1

    def test_extract_raw_texts_parses_gbk_entities_section(self, tmp_path):
        parser = DxfParser()
        dxf_path = tmp_path / "raw-texts.dxf"
        dxf_path.write_bytes(
            (
                "0\nSECTION\n2\nENTITIES\n"
                "0\nTEXT\n5\n1FAA\n8\n"
            ).encode("ascii")
            + "电-文字".encode("gbk")
            + (
                "\n10\n-306857.3960945942\n20\n-72645.28293177998\n30\n0\n40\n350\n1\n"
            ).encode("ascii")
            + "编码感烟火灾探测器".encode("gbk")
            + "\n7\nXD2008\n0\nENDSEC\n0\nEOF\n".encode("ascii")
        )

        texts = parser._extract_raw_texts(str(dxf_path))

        assert len(texts) == 1
        assert texts[0]["content"] == "编码感烟火灾探测器"
        assert texts[0]["handle"] == "1FAA"
        assert texts[0]["layer"] == "电-文字"
