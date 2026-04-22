import time
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.logging import logger
from app.models import Account, Order, Position, Trade, User

router = APIRouter()


def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/health")
async def health_check():
    """系统健康检查"""
    start_time = time.time()
    
    # Basic health check
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "Leek Trader Backend",
        "response_time": f"{((time.time() - start_time) * 1000):.2f}ms"
    }
    
    logger.info("Health check performed")
    return health_status


@router.get("/metrics")
async def get_metrics(db: Session = Depends(get_db)):
    """获取系统指标"""
    start_time = time.time()
    
    # Count users
    user_count = db.query(func.count(User.id)).scalar() or 0
    
    # Count accounts
    account_count = db.query(func.count(Account.id)).scalar() or 0
    
    # Count positions
    position_count = db.query(func.count(Position.id)).scalar() or 0
    
    # Count orders
    order_count = db.query(func.count(Order.id)).scalar() or 0
    
    # Count trades
    trade_count = db.query(func.count(Trade.id)).scalar() or 0
    
    # Calculate total equity
    total_equity_result = db.query(func.sum(Account.total_equity)).scalar()
    total_equity = float(total_equity_result) if total_equity_result else 0.0
    
    metrics = {
        "timestamp": datetime.utcnow().isoformat(),
        "users": user_count,
        "accounts": account_count,
        "positions": position_count,
        "orders": order_count,
        "trades": trade_count,
        "total_equity": total_equity,
        "response_time": f"{((time.time() - start_time) * 1000):.2f}ms"
    }
    
    logger.info("Metrics collected")
    return metrics


@router.get("/logs/latest")
async def get_latest_logs(limit: int = 50):
    """获取最新日志"""
    try:
        log_file = "/Users/diaoff/code/vibe/leek-trader/backend/logs/app.log"
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        latest_logs = lines[-limit:] if len(lines) > limit else lines
        
        return {
            "logs": latest_logs,
            "count": len(latest_logs),
            "total": len(lines)
        }
    except Exception as e:
        logger.error(f"Error reading logs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to read logs"
        )


@router.get("/system/stats")
async def get_system_stats():
    """获取系统统计信息"""
    import psutil
    import os
    
    try:
        # Get system stats
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        stats = {
            "cpu_percent": cpu_percent,
            "memory": {
                "total": memory.total,
                "available": memory.available,
                "used": memory.used,
                "percent": memory.percent
            },
            "disk": {
                "total": disk.total,
                "used": disk.used,
                "free": disk.free,
                "percent": disk.percent
            },
            "pid": os.getpid(),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return stats
    except ImportError:
        return {
            "message": "psutil not installed, system stats not available",
            "timestamp": datetime.utcnow().isoformat()
        }
