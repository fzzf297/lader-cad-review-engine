"""
SQLAlchemy 数据库模型定义
"""
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    String,
    Text,
    Float,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    Enum as SQLEnum,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from .database import Base


class FileStatus(str, enum.Enum):
    """文件状态枚举"""
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    REVIEWED = "reviewed"
    ERROR = "error"


class SeverityLevel(str, enum.Enum):
    """问题严重程度枚举"""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class IssueSource(str, enum.Enum):
    """问题来源枚举"""
    RULE = "rule"
    LLM = "llm"
    BOTH = "both"


class DWGFile(Base):
    """DWG/DXF 文件模型"""
    __tablename__ = "dwg_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    original_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    suffix: Mapped[str] = mapped_column(String(20), default="")
    converted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    upload_time: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    status: Mapped[FileStatus] = mapped_column(
        SQLEnum(FileStatus),
        default=FileStatus.UPLOADED,
        nullable=False
    )

    # 关联关系
    reviews: Mapped[List["ReviewRecord"]] = relationship(
        "ReviewRecord",
        back_populates="dwg_file",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<DWGFile(id={self.id}, filename={self.filename})>"


class ContractFile(Base):
    """合同文件模型"""
    __tablename__ = "contract_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    original_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    suffix: Mapped[str] = mapped_column(String(20), default="")
    converted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    upload_time: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    # 关联关系
    reviews: Mapped[List["ReviewRecord"]] = relationship(
        "ReviewRecord",
        back_populates="contract_file"
    )

    def __repr__(self) -> str:
        return f"<ContractFile(id={self.id}, filename={self.filename})>"


class ReviewRecord(Base):
    """审核记录模型"""
    __tablename__ = "review_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dwg_file_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("dwg_files.id", ondelete="CASCADE"),
        nullable=False
    )
    contract_file_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("contract_files.id", ondelete="SET NULL"),
        nullable=True
    )
    review_time: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    assessment: Mapped[str] = mapped_column(String(50), default="")
    enable_llm: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    result_json: Mapped[str] = mapped_column(Text, default="{}")

    # 关联关系
    dwg_file: Mapped["DWGFile"] = relationship(
        "DWGFile",
        back_populates="reviews"
    )
    contract_file: Mapped[Optional["ContractFile"]] = relationship(
        "ContractFile",
        back_populates="reviews"
    )
    issues: Mapped[List["ReviewIssue"]] = relationship(
        "ReviewIssue",
        back_populates="review",
        cascade="all, delete-orphan"
    )

    # 索引
    __table_args__ = (
        Index("ix_review_records_dwg_file_id", "dwg_file_id"),
        Index("ix_review_records_contract_file_id", "contract_file_id"),
        Index("ix_review_records_review_time", "review_time"),
    )

    def __repr__(self) -> str:
        return f"<ReviewRecord(id={self.id}, score={self.overall_score})>"


class ReviewIssue(Base):
    """审核问题模型"""
    __tablename__ = "review_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("review_records.id", ondelete="CASCADE"),
        nullable=False
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[SeverityLevel] = mapped_column(
        SQLEnum(SeverityLevel),
        default=SeverityLevel.WARNING,
        nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str] = mapped_column(String(255), default="")
    suggestion: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[IssueSource] = mapped_column(
        SQLEnum(IssueSource),
        default=IssueSource.RULE,
        nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    # 关联关系
    review: Mapped["ReviewRecord"] = relationship(
        "ReviewRecord",
        back_populates="issues"
    )

    # 索引
    __table_args__ = (
        Index("ix_review_issues_review_id", "review_id"),
        Index("ix_review_issues_category", "category"),
        Index("ix_review_issues_severity", "severity"),
    )

    def __repr__(self) -> str:
        return f"<ReviewIssue(id={self.id}, category={self.category}, severity={self.severity})>"
