"""东方财富数据采集器"""

import akshare as ak
import pandas as pd
from rich.console import Console
from rich.progress import track

from src.collectors.base import BaseCollector
from src.collectors.registry import register_collector

console = Console()


@register_collector
class EastMoneyCollector(BaseCollector):
    """
    东方财富数据采集器。

    通过 akshare 获取东方财富的概念板块数据和个股信息。
    """

    name = "eastmoney"
    description = "东方财富概念板块和个股信息采集"

    def collect_full(self, stocks: list[dict], limit: int | None = None) -> None:
        """全量采集：获取所有概念板块及成分股，反向建立股票→概念映射"""
        console.print("[bold blue]【东方财富】开始全量采集...[/bold blue]")

        # 第一步：获取所有概念板块
        concept_mapping = self._build_concept_mapping()

        # 第二步：为每只股票整理数据
        target_stocks = stocks[:limit] if limit else stocks
        success_count = 0
        error_count = 0

        for stock in track(target_stocks, description="[东方财富] 采集个股信息"):
            code = stock["code"]
            try:
                data = self._collect_stock(code, stock["name"], concept_mapping)
                self.save_draft(code, data)
                success_count += 1
            except Exception as e:
                console.print(f"[yellow]  跳过 {code} {stock['name']}: {e}[/yellow]")
                error_count += 1

            self.sleep()

        console.print(
            f"[green]【东方财富】全量采集完成: "
            f"成功 {success_count}, 失败 {error_count}[/green]"
        )

    def collect_incremental(self, stocks: list[dict]) -> None:
        """增量采集：仅采集尚未采集的股票"""
        console.print("[bold blue]【东方财富】开始增量采集...[/bold blue]")

        # 过滤出未采集的股票
        new_stocks = [s for s in stocks if not self.has_draft(s["code"])]
        if not new_stocks:
            console.print("[dim]【东方财富】无新增股票需要采集[/dim]")
            return

        console.print(f"[blue]发现 {len(new_stocks)} 只新股票[/blue]")
        self.collect_full(new_stocks)

    def _build_concept_mapping(self) -> dict[str, list[str]]:
        """
        构建 股票代码 → 所属概念板块列表 的映射。

        通过获取所有概念板块 → 获取每个板块的成分股 → 反向映射。
        """
        console.print("[blue]  获取概念板块列表...[/blue]")
        try:
            concepts_df = ak.stock_board_concept_name_em()
        except Exception as e:
            console.print(f"[red]  获取概念板块列表失败: {e}[/red]")
            return {}

        # 股票代码 → 概念列表
        stock_concepts: dict[str, list[str]] = {}

        for _, row in track(
            concepts_df.iterrows(),
            description="[东方财富] 解析概念板块成分股",
            total=len(concepts_df),
        ):
            concept_name = str(row.get("板块名称", "")).strip()
            if not concept_name:
                continue

            try:
                cons_df = ak.stock_board_concept_cons_em(symbol=concept_name)
                for _, srow in cons_df.iterrows():
                    scode = str(srow.get("代码", "")).strip()
                    if scode:
                        stock_concepts.setdefault(scode, []).append(concept_name)
                self.sleep()
            except Exception:
                # 部分板块可能获取不到成分股
                continue

        console.print(f"[green]  概念映射构建完成: 覆盖 {len(stock_concepts)} 只股票[/green]")
        return stock_concepts

    def _collect_stock(
        self, code: str, name: str, concept_mapping: dict[str, list[str]]
    ) -> dict:
        """采集单只股票的完整数据"""
        data = {
            "code": code,
            "name": name,
            "concepts": concept_mapping.get(code, []),
            "info": {},
        }

        # 获取个股基本信息
        try:
            info_df = ak.stock_individual_info_em(symbol=code)
            if info_df is not None and not info_df.empty:
                info_dict = {}
                for _, row in info_df.iterrows():
                    key = str(row.iloc[0]).strip()
                    val = str(row.iloc[1]).strip()
                    if key and val:
                        info_dict[key] = val
                data["info"] = info_dict
        except Exception:
            pass

        return data
