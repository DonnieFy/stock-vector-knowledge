#!/usr/bin/env python3
"""
每日固定拉取异动、产业、时间线数据的定时任务入口。
"""

import sys
from datetime import datetime
from pathlib import Path
from rich.console import Console

# 确保项目根目录在 sys.path 中，以便支持绝对路径导入
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from src.collectors.jiuyangongshe import (
    fetch_and_save,
    fetch_and_save_industry,
    fetch_and_save_timeline
)

console = Console()

def run_daily():
    today = datetime.now().strftime("%Y-%m-%d")
    console.print(f"[bold green]===== 开始执行每日定时任务: {today} =====[/bold green]")
    
    # 1.拉取每日异动
    console.print(f"\n[bold blue]1. 拉取异动数据 ({today})[/bold blue]")
    fetch_and_save(today)
    
    # 2.拉取产业记录
    console.print(f"\n[bold blue]2. 拉取产业记录[/bold blue]")
    fetch_and_save_industry()
    
    # 3.拉取时间线事件
    console.print(f"\n[bold blue]3. 拉取时间线事件[/bold blue]")
    fetch_and_save_timeline()
    
    console.print(f"\n[bold green]===== 每日定时任务执行完成: {today} =====[/bold green]")

if __name__ == "__main__":
    run_daily()
