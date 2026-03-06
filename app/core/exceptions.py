from typing import Optional, Any


class AppException(Exception):
    """业务异常基类"""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, detail: Optional[Any] = None):
        self.message = message
        self.detail = detail
        super().__init__(message)


class NotFoundException(AppException):
    """404 — 标的不存在等"""
    status_code = 404
    error_code = "NOT_FOUND"


class DuplicateException(AppException):
    """400 — 标的已存在等"""
    status_code = 400
    error_code = "DUPLICATE"


class DataSourceException(AppException):
    """503 — 上游接口不可用"""
    status_code = 503
    error_code = "DATA_SOURCE_UNAVAILABLE"


class ValidationException(AppException):
    """422 — 参数校验失败"""
    status_code = 422
    error_code = "VALIDATION_ERROR"


class ServiceException(AppException):
    """500 — 内部服务错误"""
    status_code = 500
    error_code = "SERVICE_ERROR"
