"""腾讯股票数据采集器 - 基于 qt.gtimg.cn API"""

import time
import requests
from rich.console import Console
from rich.progress import track

from src.collectors.base import BaseCollector
from src.collectors.registry import register_collector

console = Console()

# 腾讯股票API支持批量查询，一次最多查询约50只
BATCH_SIZE = 50

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 2  # 秒


def _market_prefix(code: str) -> str:
    """根据股票代码判断市场前缀（腾讯API格式）"""
    if code.startswith(("6", "9")):
        return f"sh{code}"
    elif code.startswith(("0", "2", "3")):
        return f"sz{code}"
    elif code.startswith("4") or code.startswith("8"):
        return f"bj{code}"
    else:
        return f"sz{code}"


def _parse_tencent_line(line: str) -> dict | None:
    """
    解析腾讯股票API返回的单行数据。

    格式: v_sh600519="1~贵州茅台~600519~1500.00~1490.00~1495.00~50000~..."
    字段含义(主要):
        0: 未知
        1: 股票名称
        2: 代码
        3: 最新价
        4: 昨收
        5: 今开
        6: 成交量(手)
        7: 外盘
        8: 内盘
        9-28: 买卖盘口
        29: 时间
        30: 涨跌
        31: 涨跌幅(%)
        32: 最高
        33: 最低
        34: 价格/成交量/成交额
        35: 成交量(手)
        36: 成交额(万)
        37: 换手率(%)
        38: 市盈率
        39: 未知
        40: 最高
        41: 最低
        42: 振幅(%)
        43: 流通市值
        44: 总市值
        45: 市净率
        46: 涨停价
        47: 跌停价
    """
    if "=" not in line:
        return None

    # 提取引号中的数据
    parts_match = line.split('"')
    if len(parts_match) < 2 or not parts_match[1]:
        return None

    parts = parts_match[1].split("~")
    if len(parts) < 48:
        return None

    code = parts[2]
    if not code:
        return None

    try:
        return {
            "code": code,
            "name": parts[1],
            "price": parts[3],
            "prev_close": parts[4],
            "open": parts[5],
            "volume": parts[6],  # 成交量(手)
            "turnover": parts[37],  # 成交额(万)
            "turnover_rate": parts[38],  # 换手率(%)
            "pe": parts[39],  # 市盈率
            "high": parts[33],  # 最高价
            "low": parts[34] if len(parts[34]) > 2 else parts[42],  # 最低价
            "amplitude": parts[43],  # 振幅(%)
            "market_cap_float": parts[44],  # 流通市值(亿)
            "market_cap_total": parts[45],  # 总市值(亿)
            "pb": parts[46],  # 市净率
        }
    except (IndexError, ValueError):
        return None


def _fetch_batch(codes: list[str]) -> list[dict]:
    """
    批量获取股票数据。

    Args:
        codes: 股票代码列表（已带市场前缀，如 sh600519）

    Returns:
        解析后的股票数据列表
    """
    symbols = ",".join(codes)
    url = f"https://qt.gtimg.cn/q={symbols}"

    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(url, headers=_HEADERS, timeout=15)
            if r.status_code == 200:
                results = []
                for line in r.text.strip().split("\n"):
                    data = _parse_tencent_line(line.strip())
                    if data:
                        results.append(data)
                return results
        except requests.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)

    return []


@register_collector
class TencentCollector(BaseCollector):
    """
    腾讯股票数据采集器。

    通过 qt.gtimg.cn API 批量获取个股基本行情信息。
    支持批量查询，效率高。
    """

    name = "tencent"
    description = "腾讯个股行情信息采集"

    def collect_full(self, stocks: list[dict], limit: int | None = None) -> None:
        """全量采集：批量获取所有股票的行情信息"""
        console.print("[bold blue]【腾讯】开始全量采集...[/bold blue]")

        target_stocks = stocks[:limit] if limit else stocks
        success_count = 0
        error_count = 0

        # 按批次处理
        batches = []
        for i in range(0, len(target_stocks), BATCH_SIZE):
            batch = target_stocks[i : i + BATCH_SIZE]
            batches.append(batch)

        for batch in track(batches, description="[腾讯] 批量采集行情"):
            # 构建带市场前缀的代码列表
            prefixed_codes = [_market_prefix(s["code"]) for s in batch]

            # 批量获取
            results = _fetch_batch(prefixed_codes)
            result_map = {r["code"]: r for r in results}

            # 保存每只股票
            for stock in batch:
                code = stock["code"]
                if code in result_map:
                    self.save_draft(code, result_map[code])
                    success_count += 1
                else:
                    # 保存空数据以标记已尝试
                    self.save_draft(code, {
                        "code": code,
                        "name": stock["name"],
                    })
                    error_count += 1

            self.sleep()

        console.print(
            f"[green]【腾讯】全量采集完成: "
            f"成功 {success_count}, 无数据 {error_count}[/green]"
        )

    def collect_incremental(self, stocks: list[dict]) -> None:
        """增量采集：仅采集尚未采集的股票"""
        console.print("[bold blue]【腾讯】开始增量采集...[/bold blue]")

        new_stocks = [s for s in stocks if not self.has_draft(s["code"])]
        if not new_stocks:
            console.print("[dim]【腾讯】无新增股票需要采集[/dim]")
            return

        console.print(f"[blue]发现 {len(new_stocks)} 只新股票[/blue]")
        self.collect_full(new_stocks)
