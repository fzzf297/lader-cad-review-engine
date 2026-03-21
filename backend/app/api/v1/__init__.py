"""
API v1 模块
"""
from .router import api_router
from .upload import router as upload_router
from .review import router as review_router

__all__ = ["api_router", "upload_router", "review_router"]