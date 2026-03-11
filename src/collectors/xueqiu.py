"""雪球数据采集器（预留框架）"""

from rich.console import Console

from src.collectors.base import BaseCollector
from src.collectors.registry import register_collector

console = Console()


@register_collector
class XueqiuCollector(BaseCollector):
    """
    雪球数据采集器（预留）。

    雪球需要手动设置Cookie，且反爬较严格。
    建议通过 .agent/skills/collect_browser.md SKILL
    使用 Claude Code 浏览器工具半自动化采集。
    """

    name = "xueqiu"
    description = "雪球数据采集（需手动Cookie，建议用浏览器SKILL）"

    def collect_full(self, stocks: list[dict], limit: int | None = None) -> None:
        console.print(
            "[yellow]【雪球】采集器尚未完整实现。[/yellow]\n"
            "[dim]建议使用 Claude Code 的浏览器 SKILL 半自动采集：[/dim]\n"
            "[dim]  参见 .agent/skills/collect_browser.md[/dim]"
        )

    def collect_incremental(self, stocks: list[dict]) -> None:
        console.print("[yellow]【雪球】增量采集暂未实现[/yellow]")
