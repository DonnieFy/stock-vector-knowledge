"""合并多来源草稿数据"""

import json
from pathlib import Path

from rich.console import Console
from rich.progress import track

from src.config import get_config

console = Console()


def merge_stock_drafts(stock_code: str) -> dict | None:
    """
    合并同一只股票来自不同平台的草稿数据。

    Args:
        stock_code: 股票代码

    Returns:
        合并后的数据字典，如果没有任何数据则返回 None
    """
    config = get_config()
    drafts_dir = config.drafts_dir
    merged: dict = {
        "code": stock_code,
        "name": "",
        "concepts_eastmoney": [],
        "concepts_ths": [],
        "industry": "",
        "info": {},
        "sources": [],
    }

    has_data = False

    # 遍历所有来源目录
    for source_dir in drafts_dir.iterdir():
        if not source_dir.is_dir():
            continue
        draft_file = source_dir / f"{stock_code}.json"
        if not draft_file.exists():
            continue

        with open(draft_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        has_data = True
        source_name = source_dir.name
        merged["sources"].append(source_name)

        # 合并名称
        if data.get("name") and not merged["name"]:
            merged["name"] = data["name"]

        # 合并概念和信息
        if source_name == "eastmoney":
            merged["concepts_eastmoney"] = data.get("concepts", [])
            merged["info"].update(data.get("info", {}))
        elif source_name == "ths":
            merged["concepts_ths"] = data.get("concepts_ths", [])
            if data.get("industry"):
                merged["industry"] = data["industry"]
        elif source_name == "tencent":
            # 腾讯行情数据合并到 info
            for key in ("price", "prev_close", "open", "volume", "turnover",
                        "turnover_rate", "pe", "high", "low", "amplitude",
                        "market_cap_float", "market_cap_total", "pb"):
                if data.get(key):
                    merged["info"][key] = data[key]

        # 通用：合并其他自定义字段
        for key, value in data.items():
            if key.startswith("_") or key in (
                "code", "name", "concepts", "concepts_ths", "info",
                "industry", "price", "prev_close", "open", "volume",
                "turnover", "turnover_rate", "pe", "high", "low",
                "amplitude", "market_cap_float", "market_cap_total", "pb",
            ):
                continue
            merged[key] = value

    if not has_data:
        return None

    return merged


def merge_all_drafts(save: bool = True) -> list[dict]:
    """
    合并所有股票的草稿数据。

    Args:
        save: 是否将合并结果保存到 data/drafts/merged/

    Returns:
        所有合并后的数据列表
    """
    config = get_config()
    drafts_dir = config.drafts_dir

    # 收集所有股票代码
    all_codes: set[str] = set()
    for source_dir in drafts_dir.iterdir():
        if not source_dir.is_dir() or source_dir.name == "merged":
            continue
        for f in source_dir.glob("*.json"):
            code = f.stem
            if code != "stock_list":
                all_codes.add(code)

    if not all_codes:
        console.print("[yellow]草稿箱为空，请先执行采集[/yellow]")
        return []

    console.print(f"[blue]发现 {len(all_codes)} 只股票的草稿数据[/blue]")

    results = []
    merged_dir = drafts_dir / "merged"
    if save:
        merged_dir.mkdir(parents=True, exist_ok=True)

    for code in track(sorted(all_codes), description="合并草稿数据"):
        merged = merge_stock_drafts(code)
        if merged:
            results.append(merged)
            if save:
                output_path = merged_dir / f"{code}.json"
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(merged, f, ensure_ascii=False, indent=2)

    console.print(f"[green]合并完成: {len(results)} 只股票[/green]")
    return results
