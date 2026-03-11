"""采集器基类"""

import json
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console

from src.config import get_config

console = Console()


class BaseCollector(ABC):
    """
    数据采集器基类。

    所有采集器需继承此类并实现 collect_full 和 collect_incremental 方法。
    使用 @register_collector 装饰器完成自注册。
    """

    # 子类必须定义
    name: str = ""
    description: str = ""

    def __init__(self):
        self.config = get_config()
        self._drafts_dir = self.config.drafts_dir / self.name
        self._drafts_dir.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def collect_full(self, stocks: list[dict], limit: int | None = None) -> None:
        """
        全量采集。

        Args:
            stocks: 股票列表 [{code, name, market}, ...]
            limit: 限制采集数量（调试用）
        """
        ...

    @abstractmethod
    def collect_incremental(self, stocks: list[dict]) -> None:
        """
        增量采集（仅采集新增或变更的数据）。

        Args:
            stocks: 股票列表
        """
        ...

    def save_draft(self, stock_code: str, data: dict[str, Any]) -> Path:
        """
        将采集数据存入草稿箱。

        Args:
            stock_code: 股票代码
            data: 采集到的数据

        Returns:
            保存的文件路径
        """
        # 添加元数据
        data["_meta"] = {
            "source": self.name,
            "stock_code": stock_code,
            "collected_at": datetime.now().isoformat(),
        }

        file_path = self._drafts_dir / f"{stock_code}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return file_path

    def load_draft(self, stock_code: str) -> dict[str, Any] | None:
        """加载已有草稿数据"""
        file_path = self._drafts_dir / f"{stock_code}.json"
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def has_draft(self, stock_code: str) -> bool:
        """检查是否已有草稿"""
        return (self._drafts_dir / f"{stock_code}.json").exists()

    def sleep(self):
        """请求间隔，避免被限流"""
        interval = self.config.request_interval
        if interval > 0:
            time.sleep(interval)
