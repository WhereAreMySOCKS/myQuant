"""通用类型转换工具函数。"""

import logging

logger = logging.getLogger(__name__)


def safe_float(val, default: float = 0.0) -> float:
    """安全地将任意值转换为 float，转换失败时返回 default。

    Args:
        val: 待转换的值（字符串、数字、None 等）。
        default: 转换失败时的默认值，默认为 0.0。

    Returns:
        转换后的 float 值，或 default。
    """
    try:
        return float(val)
    except (ValueError, TypeError):
        return default
