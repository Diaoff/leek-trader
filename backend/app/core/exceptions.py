from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from pydantic import ValidationError
import logging

from app.core.logging import logger


class AppException(HTTPException):
    """应用基础异常类"""
    def __init__(self, status_code: int, detail: str, error_code: str = "APP_ERROR"):
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code


class AuthenticationException(AppException):
    """认证异常"""
    def __init__(self, detail: str = "认证失败"):
        super().__init__(status_code=401, detail=detail, error_code="AUTH_ERROR")


class PermissionException(AppException):
    """权限异常"""
    def __init__(self, detail: str = "权限不足"):
        super().__init__(status_code=403, detail=detail, error_code="PERMISSION_ERROR")


class ValidationException(AppException):
    """验证异常"""
    def __init__(self, detail: str = "参数验证失败"):
        super().__init__(status_code=422, detail=detail, error_code="VALIDATION_ERROR")


class NotFoundException(AppException):
    """资源不存在异常"""
    def __init__(self, detail: str = "资源不存在"):
        super().__init__(status_code=404, detail=detail, error_code="NOT_FOUND_ERROR")


class BusinessException(AppException):
    """业务逻辑异常"""
    def __init__(self, detail: str = "业务逻辑错误"):
        super().__init__(status_code=400, detail=detail, error_code="BUSINESS_ERROR")


class ServerException(AppException):
    """服务器内部异常"""
    def __init__(self, detail: str = "服务器内部错误"):
        super().__init__(status_code=500, detail=detail, error_code="SERVER_ERROR")


async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器"""
    if isinstance(exc, AppException):
        # 处理自定义异常
        logger.error(f"AppException: {exc.detail} (code: {exc.error_code})")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.error_code,
                    "message": exc.detail
                }
            }
        )
    elif isinstance(exc, HTTPException):
        # 处理 FastAPI 内置 HTTP 异常
        logger.error(f"HTTPException: {exc.detail} (status: {exc.status_code})")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": "HTTP_ERROR",
                    "message": exc.detail
                }
            }
        )
    elif isinstance(exc, ValidationError):
        # 处理 Pydantic 验证异常
        logger.error(f"ValidationError: {exc.errors()}")
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "参数验证失败",
                    "details": exc.errors()
                }
            }
        )
    elif isinstance(exc, SQLAlchemyError):
        # 处理数据库异常
        logger.error(f"SQLAlchemyError: {str(exc)}")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "DATABASE_ERROR",
                    "message": "数据库操作失败"
                }
            }
        )
    else:
        # 处理其他未预期异常
        logger.error(f"Unexpected error: {str(exc)}")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "UNEXPECTED_ERROR",
                    "message": "服务器内部错误"
                }
            }
        )


def setup_exception_handlers(app):
    """设置异常处理器"""
    app.exception_handler(Exception)(global_exception_handler)
