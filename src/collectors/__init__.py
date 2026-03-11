"""数据采集器模块"""

from src.collectors.registry import get_collector, get_all_collectors, list_collectors
from src.collectors.stock_list import get_stock_list

# 导入采集器模块以触发 @register_collector 注册
from src.collectors import ths  # noqa: F401
from src.collectors import tencent  # noqa: F401

# 保留旧模块但不自动注册（eastmoney API 已失效）
# from src.collectors import eastmoney  # noqa: F401

__all__ = ["get_collector", "get_all_collectors", "list_collectors", "get_stock_list"]
