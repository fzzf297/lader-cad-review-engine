"""
文件上传 API

当前审核链路只支持可直接解析的 DXF。
DWG 文件在现阶段统一拒绝上传，避免“上传成功但无法审核”的误导体验。
"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
import shutil
import tempfile
import uuid
import logging

from ...core.config import settings
from ...services.file_registry import FileRecord, get_file_registry
logger = logging.getLogger(__name__)

router = APIRouter()


def _get_transient_upload_path(file_id: str, suffix: str) -> Path:
    """将上传文件写入系统临时目录，避免长期占用项目工作区。"""
    upload_dir = Path(tempfile.gettempdir()) / "cad-review-engine"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir / f"{file_id}{suffix}"


class UploadResponse(BaseModel):
    """上传响应"""
    file_id: str
    filename: str
    file_type: str
    file_path: str
    status: str
    message: Optional[str] = None
    converted: bool = False  # 是否经过转换
    uploaded_at: str = ""


class FileInfoResponse(BaseModel):
    """文件信息响应"""
    file_id: str
    filename: str
    file_type: str
    file_size: int
    status: str
    converted: bool = False
    uploaded_at: str = ""


class FileListItemResponse(BaseModel):
    """文件列表项"""
    file_id: str
    filename: str
    file_type: str
    file_size: int
    status: str
    converted: bool = False
    uploaded_at: str


class FileListResponse(BaseModel):
    """文件列表响应"""
    files: List[FileListItemResponse]
    total: int


@router.post("/dwg", response_model=UploadResponse)
async def upload_dwg(
    file: UploadFile = File(...)
):
    """上传图纸文件（当前仅支持 DXF）"""

    # 验证文件扩展名
    suffix = Path(file.filename).suffix.lower()
    if suffix == ".dwg":
        raise HTTPException(400, "当前版本暂不支持 DWG 上传，请先将文件转换为 DXF 后再上传")
    if suffix != ".dxf":
        raise HTTPException(400, "只支持 DXF 文件")

    # 生成文件 ID
    file_id = str(uuid.uuid4())

    # 保存到系统临时目录
    file_path = _get_transient_upload_path(file_id, suffix)

    try:
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        logger.error(f"文件保存失败: {e}")
        raise HTTPException(500, f"文件保存失败: {str(e)}")

    record = get_file_registry().register(FileRecord(
        file_id=file_id,
        filename=file.filename,
        file_type="dwg",
        file_path=str(file_path),
        original_path=None,
        suffix=suffix,
        status="uploaded",
        converted=False,
    ))

    return UploadResponse(
        file_id=record.file_id,
        filename=record.filename,
        file_type="dwg",
        file_path=record.file_path,
        status=record.status,
        message="DXF 文件上传成功，可以进行审核",
        converted=False,
        uploaded_at=record.uploaded_at,
    )


@router.post("/contract", response_model=UploadResponse)
async def upload_contract(file: UploadFile = File(...)):
    """上传合同文件 (Word/PDF)"""

    # 验证文件扩展名
    suffix = Path(file.filename).suffix.lower()
    if suffix not in [".doc", ".docx", ".pdf"]:
        raise HTTPException(400, "只支持 Word 或 PDF 文件")

    # 生成文件 ID
    file_id = str(uuid.uuid4())

    # 保存到系统临时目录
    file_path = _get_transient_upload_path(file_id, suffix)

    try:
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        logger.error(f"文件保存失败: {e}")
        raise HTTPException(500, f"文件保存失败: {str(e)}")

    record = get_file_registry().register(FileRecord(
        file_id=file_id,
        filename=file.filename,
        file_type="contract",
        file_path=str(file_path),
        suffix=suffix,
        status="uploaded",
    ))

    return UploadResponse(
        file_id=record.file_id,
        filename=record.filename,
        file_type="contract",
        file_path=record.file_path,
        status=record.status,
        message="合同文件上传成功，可以进行分析",
        uploaded_at=record.uploaded_at,
    )


@router.get("/list", response_model=FileListResponse)
async def list_files(file_type: Optional[str] = None):
    """获取已上传文件列表"""
    records = get_file_registry().list(file_type=file_type)
    items = []
    for record in records:
        file_path = Path(record.file_path)
        items.append(FileListItemResponse(
            file_id=record.file_id,
            filename=record.filename,
            file_type=record.file_type,
            file_size=file_path.stat().st_size if file_path.exists() else 0,
            status=record.status,
            converted=record.converted,
            uploaded_at=record.uploaded_at,
        ))

    return FileListResponse(files=items, total=len(items))


@router.get("/{file_id}", response_model=FileInfoResponse)
async def get_file_info(file_id: str):
    """获取文件信息"""
    record = get_file_registry().get(file_id)
    if not record:
        raise HTTPException(404, "文件不存在")

    file_path = Path(record.file_path)

    return FileInfoResponse(
        file_id=record.file_id,
        filename=record.filename,
        file_type=record.file_type,
        file_size=file_path.stat().st_size if file_path.exists() else 0,
        status=record.status,
        converted=record.converted,
        uploaded_at=record.uploaded_at,
    )
