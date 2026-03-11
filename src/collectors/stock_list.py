"""A股股票列表管理"""

import json
import time
from datetime import datetime
from pathlib import Path

import akshare as ak
import pandas as pd
from rich.console import Console

from src.config import get_config

console = Console()

# 缓存文件路径
_CACHE_FILE = "stock_list.json"


def get_stock_list(refresh: bool = False) -> list[dict]:
    """
    获取全A股股票列表。

    Args:
        refresh: 是否强制刷新（忽略缓存）

    Returns:
        股票列表 [{code, name, market}, ...]
    """
    config = get_config()
    cache_path = config.drafts_dir / _CACHE_FILE
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    # 尝试读取缓存
    if not refresh and cache_path.exists():
        with open(cache_path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        # 缓存有效期: 当天
        cached_date = cached.get("date", "")
        today = datetime.now().strftime("%Y-%m-%d")
        if cached_date == today:
            console.print(f"[dim]从缓存加载股票列表: {len(cached['stocks'])} 只[/dim]")
            return cached["stocks"]

    # 从 akshare 获取（带重试 + 备用API）
    console.print("[bold blue]正在获取A股股票列表...[/bold blue]")
    df = None

    # 策略1: stock_zh_a_spot_em (数据更丰富)
    for attempt in range(2):
        try:
            df = ak.stock_zh_a_spot_em()
            console.print("[dim]使用 stock_zh_a_spot_em 获取成功[/dim]")
            break
        except Exception as e:
            wait = 3 * (2 ** attempt)
            console.print(f"[yellow]stock_zh_a_spot_em 失败 (第{attempt+1}次): {e}, {wait}秒后重试...[/yellow]")
            time.sleep(wait)

    # 策略2: stock_info_a_code_name (备用，更稳定)
    if df is None:
        console.print("[yellow]切换到备用API: stock_info_a_code_name[/yellow]")
        try:
            df = ak.stock_info_a_code_name()
            console.print("[dim]使用 stock_info_a_code_name 获取成功[/dim]")
        except Exception as e2:
            console.print(f"[red]备用API也失败: {e2}[/red]")
            # 尝试使用过期缓存
            if cache_path.exists():
                with open(cache_path, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                console.print(f"[yellow]使用过期缓存: {len(cached['stocks'])} 只[/yellow]")
                return cached["stocks"]
            raise

    stocks = []
    for _, row in df.iterrows():
        # 兼容 stock_zh_a_spot_em (代码/名称) 和 stock_info_a_code_name (code/name)
        code = str(row.get("代码", row.get("code", ""))).strip()
        name = str(row.get("名称", row.get("name", ""))).strip()
        if not code or not name:
            continue

        # 判断市场
        if code.startswith("6"):
            market = "SH"
        elif code.startswith(("0", "3")):
            market = "SZ"
        elif code.startswith(("4", "8")):
            market = "BJ"
        else:
            market = "OTHER"

        stocks.append({
            "code": code,
            "name": name,
            "market": market,
        })

    # 保存缓存
    cache_data = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "count": len(stocks),
        "stocks": stocks,
    }
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)

    console.print(f"[green]获取到 {len(stocks)} 只A股股票[/green]")
    return stocks
