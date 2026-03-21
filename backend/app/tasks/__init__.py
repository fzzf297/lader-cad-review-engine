"""
Celery 异步任务模块

支持大文件异步处理和长时间运行的审核任务
"""
from .celery_app import celery_app

__all__ = ["celery_app"]