"""
API v1 路由
"""
from fastapi import APIRouter
from .upload import router as upload_router
from .review import router as review_router
from .tasks import router as tasks_router
from .parse import router as parse_router
from .validate import router as validate_router

api_router = APIRouter()
api_router.include_router(upload_router, prefix="/upload", tags=["upload"])
api_router.include_router(review_router, prefix="/review", tags=["review"])
api_router.include_router(tasks_router, prefix="/tasks", tags=["tasks"])
api_router.include_router(parse_router, prefix="/parse", tags=["parse"])
api_router.include_router(validate_router, prefix="/validate", tags=["validate"])