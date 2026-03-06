"""tests/test_data_fetcher.py — 测试 _exchange_prefix() 与 safe_float() 边界情况。"""

import pytest

from app.services.data_fetcher import _exchange_prefix
from app.utils.convert import safe_float


# ==================== _exchange_prefix ====================

class TestExchangePrefix:
    # 上交所 —— 主板 6xxxxx
    def test_sh_main_board(self):
        assert _exchange_prefix("600000") == "sh"
        assert _exchange_prefix("601318") == "sh"

    # 上交所 —— ETF/LOF 5xxxxx
    def test_sh_etf(self):
        assert _exchange_prefix("510300") == "sh"
        assert _exchange_prefix("588000") == "sh"

    # 深交所 —— 主板 000/001
    def test_sz_main_board(self):
        assert _exchange_prefix("000001") == "sz"
        assert _exchange_prefix("001234") == "sz"

    # 深交所 —— 中小板 002/003
    def test_sz_sme_board(self):
        assert _exchange_prefix("002415") == "sz"
        assert _exchange_prefix("003816") == "sz"

    # 深交所 —— 创业板 300/301
    def test_sz_gem_board(self):
        assert _exchange_prefix("300750") == "sz"
        assert _exchange_prefix("301001") == "sz"

    # 北交所 —— 8xxxxx
    def test_bj_8(self):
        assert _exchange_prefix("835796") == "bj"
        assert _exchange_prefix("873586") == "bj"

    # 北交所 —— 4xxxxx
    def test_bj_4(self):
        assert _exchange_prefix("430047") == "bj"
        assert _exchange_prefix("400001") == "bj"

    # 空字符串兜底
    def test_empty_code_returns_sz(self):
        assert _exchange_prefix("") == "sz"


# ==================== safe_float ====================

class TestSafeFloat:
    def test_integer_string(self):
        assert safe_float("42") == 42.0

    def test_float_string(self):
        assert abs(safe_float("3.14") - 3.14) < 1e-9

    def test_integer_value(self):
        assert safe_float(100) == 100.0

    def test_float_value(self):
        assert safe_float(1.5) == 1.5

    def test_none_returns_default(self):
        assert safe_float(None) == 0.0

    def test_none_custom_default(self):
        assert safe_float(None, default=-1.0) == -1.0

    def test_empty_string_returns_default(self):
        assert safe_float("") == 0.0

    def test_non_numeric_string_returns_default(self):
        assert safe_float("abc") == 0.0

    def test_negative_number(self):
        assert safe_float("-0.05") == -0.05

    def test_zero_string(self):
        assert safe_float("0") == 0.0

    def test_whitespace_string_returns_default(self):
        assert safe_float("  ") == 0.0
