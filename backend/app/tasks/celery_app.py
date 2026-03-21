"""
Celery 应用配置

使用 Redis 作为 broker 和 backend
支持异步任务处理大文件审核
"""
from celery import Celery
import os

# 从环境变量读取 Redis URL，默认使用本地 Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# 创建 Celery 应用
celery_app = Celery(
    "dwg_review",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks.review_tasks"]
)

# Celery 配置
celery_app.conf.update(
    # 任务序列化
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # 结果过期时间（24小时）
    result_expires=86400,

    # 时区设置
    timezone="Asia/Shanghai",
    enable_utc=True,

    # 任务结果配置
    result_backend_transport_options={
        "master_name": "mymaster"  # Redis Sentinel 支持（如果使用）
    },

    # 任务执行配置
    task_acks_late=True,  # 任务完成后才确认，防止任务丢失
    task_reject_on_worker_lost=True,  # worker 丢失时拒绝任务
    task_track_started=True,  # 跟踪任务开始状态

    # 并发配置
    worker_prefetch_multiplier=1,  # 每次只获取一个任务，适合长任务

    # 任务路由
    task_routes={
        "app.tasks.review_tasks.process_dwg_task": {"queue": "review"},
    },

    # 任务默认配置
    task_default_retry_delay=60,  # 重试延迟 60 秒
    task_max_retries=3,  # 最大重试次数
)

# 自动发现任务
celery_app.autodiscover_tasks(["app.tasks"])