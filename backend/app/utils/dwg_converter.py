"""
DWG 到 DXF 转换器

支持的转换方式：
1. ODA File Converter (推荐)
2. LibreDWG (dwg2dxf 命令)
3. Python 在线转换服务 (备选)
"""
import subprocess
import shutil
import logging
import tempfile
import os
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class DWGConverter:
    """DWG 转 DXF 转换器"""

    def __init__(self):
        self.converter_path = self._find_converter()
        self.converter_type = self._detect_converter_type()

    def _find_converter(self) -> Optional[str]:
        """查找可用的转换器"""
        # 1. 检查 ODA File Converter (多种路径)
        oda_paths = [
            str(Path.home() / ".local" / "bin" / "ODAFileConverter.app" / "Contents" / "MacOS" / "ODAFileConverter"),  # 本地安装
            "/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter",
            "/usr/local/bin/ODAFileConverter",
            "/usr/bin/ODAFileConverter",
            "ODAFileConverter",
        ]
        for path in oda_paths:
            if os.path.exists(path):
                logger.info(f"找到 ODA File Converter: {path}")
                return path
            if shutil.which(path):
                logger.info(f"找到 ODA File Converter (in PATH): {path}")
                return path

        # 2. 检查 LibreDWG (dwg2dxf)
        if shutil.which("dwg2dxf"):
            logger.info("找到 LibreDWG (dwg2dxf)")
            return "dwg2dxf"

        # 3. 检查项目本地安装的 LibreDWG
        project_libredwg = Path(__file__).parent.parent.parent.parent / "tools" / "libredwg" / "install" / "bin" / "dwg2dxf"
        if project_libredwg.exists():
            logger.info(f"找到项目本地 LibreDWG: {project_libredwg}")
            return str(project_libredwg)

        logger.warning("未找到 DWG 转换器")
        return None

    def _detect_converter_type(self) -> Optional[str]:
        """检测转换器类型"""
        if not self.converter_path:
            return None
        if "ODAFileConverter" in self.converter_path:
            return "oda"
        if "dwg2dxf" in self.converter_path:
            return "libredwg"
        return "unknown"

    def is_available(self) -> bool:
        """检查转换器是否可用"""
        return self.converter_path is not None

    def convert(self, dwg_path: str, output_dir: Optional[str] = None) -> Tuple[bool, str, str]:
        """
        将 DWG 转换为 DXF

        Args:
            dwg_path: DWG 文件路径
            output_dir: 输出目录（默认与源文件同目录）

        Returns:
            (success, dxf_path, error_message)
        """
        if not self.converter_path:
            return False, "", "未安装 DWG 转换器。请安装 ODA File Converter 或 LibreDWG"

        dwg_path = Path(dwg_path)
        if not dwg_path.exists():
            return False, "", f"文件不存在: {dwg_path}"

        if output_dir:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
        else:
            output_dir = dwg_path.parent

        dxf_path = output_dir / (dwg_path.stem + ".dxf")

        try:
            if self.converter_type == "oda":
                return self._convert_with_oda(str(dwg_path), str(output_dir))
            elif self.converter_type == "libredwg":
                return self._convert_with_libredwg(str(dwg_path), str(dxf_path))
            else:
                return False, "", "未知的转换器类型"
        except Exception as e:
            logger.error(f"DWG 转换失败: {e}")
            return False, "", f"转换失败: {str(e)}"

    def _convert_with_oda(self, dwg_path: str, output_dir: str) -> Tuple[bool, str, str]:
        """使用 ODA File Converter 转换"""
        dwg_file = Path(dwg_path)

        # ODA 需要输入目录和输出目录
        input_dir = str(dwg_file.parent)
        filename = dwg_file.name

        # ODAFileConverter 参数:
        # ODAFileConverter "input_dir" "output_dir" "version" "recurse" "audit"
        cmd = [
            self.converter_path,
            input_dir,      # 输入目录
            output_dir,     # 输出目录
            "ACAD2018",     # DXF 版本
            "0",            # 不递归
            "0",            # 不审计
            filename        # 文件名
        ]

        logger.info(f"执行 ODA 转换: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )

        dxf_path = Path(output_dir) / (dwg_file.stem + ".dxf")

        if dxf_path.exists():
            logger.info(f"ODA 转换成功: {dxf_path}")
            return True, str(dxf_path), ""
        else:
            error = result.stderr or result.stdout or "转换失败，未生成 DXF 文件"
            logger.error(f"ODA 转换失败: {error}")
            return False, "", error

    def _convert_with_libredwg(self, dwg_path: str, dxf_path: str) -> Tuple[bool, str, str]:
        """使用 LibreDWG (dwg2dxf) 转换"""
        cmd = [
            self.converter_path,
            dwg_path,
            "-o", dxf_path
        ]

        logger.info(f"执行 LibreDWG 转换: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )

        if Path(dxf_path).exists():
            logger.info(f"LibreDWG 转换成功: {dxf_path}")
            return True, dxf_path, ""
        else:
            error = result.stderr or result.stdout or "转换失败"
            logger.error(f"LibreDWG 转换失败: {error}")
            return False, "", error


# 全局转换器实例
_converter: Optional[DWGConverter] = None


def get_converter() -> DWGConverter:
    """获取转换器实例"""
    global _converter
    if _converter is None:
        _converter = DWGConverter()
    return _converter


def convert_dwg_to_dxf(dwg_path: str, output_dir: Optional[str] = None) -> Tuple[bool, str, str]:
    """
    将 DWG 转换为 DXF

    Args:
        dwg_path: DWG 文件路径
        output_dir: 输出目录

    Returns:
        (success, dxf_path, error_message)
    """
    converter = get_converter()
    return converter.convert(dwg_path, output_dir)