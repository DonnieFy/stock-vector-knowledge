"""CLI 命令行入口"""

import click
from rich.console import Console

console = Console()


@click.group()
@click.option("--config", default=None, help="配置文件路径")
def cli(config):
    """A股题材向量知识库 (Stock Vector Knowledge)"""
    from src.config import get_config
    get_config(config)


# ──────────────── 数据采集 ────────────────


@cli.command()
@click.option("--full", is_flag=True, help="全量采集")
@click.option("--incremental", is_flag=True, help="增量采集")
@click.option("--source", default=None, help="指定采集来源 (ths, tencent)")
@click.option("--limit", default=None, type=int, help="限制采集数量（调试用）")
@click.option("--refresh-list", is_flag=True, help="强制刷新股票列表")
def collect(full, incremental, source, limit, refresh_list):
    """采集A股题材数据"""
    # 确保导入触发采集器注册
    import src.collectors.ths  # noqa: F401
    import src.collectors.tencent  # noqa: F401

    from src.collectors.stock_list import get_stock_list
    from src.collectors.registry import get_collector, get_all_collectors

    if not full and not incremental:
        console.print("[yellow]请指定 --full 或 --incremental[/yellow]")
        return

    # 获取股票列表
    stocks = get_stock_list(refresh=refresh_list)

    if source:
        collectors = [get_collector(source)]
    else:
        collectors = get_all_collectors()

    for collector in collectors:
        if full:
            collector.collect_full(stocks, limit=limit)
        else:
            collector.collect_incremental(stocks)


# ──────────────── 草稿合并 ────────────────


@cli.command()
@click.option("--stock", default=None, help="指定股票代码")
@click.option("--all", "merge_all", is_flag=True, help="合并所有股票")
def merge(stock, merge_all):
    """合并多来源草稿数据"""
    from src.processors.merge_drafts import merge_stock_drafts, merge_all_drafts

    if stock:
        result = merge_stock_drafts(stock)
        if result:
            console.print(f"[green]合并完成: {stock} {result.get('name', '')}[/green]")
            console.print(f"  来源: {result.get('sources', [])}")
            console.print(f"  东财概念: {len(result.get('concepts_eastmoney', []))} 个")
            console.print(f"  同花顺概念: {len(result.get('concepts_ths', []))} 个")
        else:
            console.print(f"[yellow]未找到 {stock} 的草稿数据[/yellow]")
    elif merge_all:
        merge_all_drafts()
    else:
        console.print("[yellow]请指定 --stock 或 --all[/yellow]")


# ──────────────── 摘要验证 ────────────────


@cli.command()
def validate():
    """验证摘要文件格式"""
    from src.processors.validate import validate_all_summaries
    validate_all_summaries()


# ──────────────── 向量化 ────────────────


@cli.command()
@click.option("--rebuild", is_flag=True, help="全量重建向量库")
@click.option("--update", is_flag=True, help="增量更新")
def vectorize(rebuild, update):
    """向量化摘要数据"""
    from src.vectordb.store import vectorize_rebuild, vectorize_update, get_stats

    if rebuild:
        count = vectorize_rebuild()
        console.print(f"[green]向量库重建完成: {count} 个文档[/green]")
    elif update:
        count = vectorize_update()
        console.print(f"[green]增量更新完成: {count} 个新文档[/green]")
    else:
        # 显示统计信息
        stats = get_stats()
        console.print(f"向量库统计:")
        console.print(f"  集合: {stats['collection']}")
        console.print(f"  文档数: {stats['document_count']}")
        console.print(f"  存储路径: {stats['db_path']}")


# ──────────────── 查询 ────────────────


@cli.command()
@click.argument("text")
@click.option("--top", default=10, help="返回数量")
def query(text, top):
    """文本相似查询（如: svk query "光伏组件"）"""
    from src.vectordb.query import query_similar_text, print_query_results
    results = query_similar_text(text, top_n=top)
    print_query_results(results, title=f'与 "{text}" 最相关的股票')


@cli.command()
@click.argument("stock_code")
@click.option("--top", default=10, help="返回数量")
def similar(stock_code, top):
    """股票相似查询（如: svk similar 600519）"""
    from src.vectordb.query import query_similar_stock, print_query_results
    results = query_similar_stock(stock_code, top_n=top)
    print_query_results(results, title=f"与 {stock_code} 题材最相似的股票")


@cli.command()
@click.argument("stock_codes", nargs=-1, required=True)
@click.option("-k", default=3, help="聚类数量")
def cluster(stock_codes, k):
    """拓扑聚类（如: svk cluster 600519 000001 300750）"""
    from src.vectordb.query import cluster_stocks, print_cluster_results
    result = cluster_stocks(list(stock_codes), n_clusters=k)
    print_cluster_results(result)


@cli.command()
@click.argument("stock_codes", nargs=-1, required=True)
@click.option("--top", default=10, help="每簇返回关键词数量")
@click.option("-k", default=5, help="聚类数量")
def analyze(stock_codes, top, k):
    """聚类+语义分析（如: svk analyze 688165 003028 002611）"""
    from src.vectordb.query import analyze_themes, print_theme_analysis
    results = analyze_themes(list(stock_codes), top_n=top, n_clusters=k)
    print_theme_analysis(results)


# ──────────────── 韭研公社 ────────────────


@cli.command("jiuyangongshe-action")
@click.option("--date", "date_str", default=None, help="指定日期 (YYYY-MM-DD)，默认今天")
@click.option("--start", "start_date", default=None, help="起始日期 (批量采集)")
@click.option("--end", "end_date", default=None, help="结束日期 (批量采集)")
@click.option("--force", is_flag=True, help="强制覆盖已存在的文件")
def jiuyangongshe_action(date_str, start_date, end_date, force):
    """采集韭研公社每日异动数据"""
    from datetime import datetime
    from src.collectors.jiuyangongshe import fetch_and_save, fetch_range, _ensure_data_dir

    # 检查认证配置
    from src.config import get_config
    config = get_config()
    if not config.jiuyangongshe_token and not (config.jiuyangongshe_phone and config.jiuyangongshe_password):
        console.print("[red]错误: 请在 config.yaml 中配置 jiuyangongshe.token，或提供 phone 和 password[/red]")
        return

    if start_date and end_date:
        # 批量采集模式
        fetch_range(start_date, end_date)
    else:
        # 单日采集模式
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")

        # 检查是否已存在
        action_dir = _ensure_data_dir()
        if (action_dir / f"{date_str}.json").exists() and not force:
            console.print(f"[yellow]{date_str} 数据已存在，使用 --force 覆盖[/yellow]")
            return

        console.print(f"[bold blue]【韭研公社】采集异动数据: {date_str}[/bold blue]")
        ok = fetch_and_save(date_str)
        if ok:
            console.print(f"[green]数据已保存到 data/jiuyangongshe/action/{date_str}.json[/green]")
        else:
            console.print("[red]采集失败，请检查网络和认证配置[/red]")


@cli.command("jiuyangongshe-industry")
def jiuyangongshe_industry():
    """采集韭研公社产业异动数据（增量合并）"""
    from src.collectors.jiuyangongshe import fetch_and_save_industry

    from src.config import get_config
    config = get_config()
    if not config.jiuyangongshe_token and not (config.jiuyangongshe_phone and config.jiuyangongshe_password):
        console.print("[red]错误: 请在 config.yaml 中配置认证信息[/red]")
        return

    fetch_and_save_industry()


@cli.command("jiuyangongshe-timeline")
def jiuyangongshe_timeline():
    """采集韭研公社事件时间线数据（增量合并）"""
    from src.collectors.jiuyangongshe import fetch_and_save_timeline

    from src.config import get_config
    config = get_config()
    if not config.jiuyangongshe_token and not (config.jiuyangongshe_phone and config.jiuyangongshe_password):
        console.print("[red]错误: 请在 config.yaml 中配置认证信息[/red]")
        return

    fetch_and_save_timeline()


# ──────────────── 工具 ────────────────


@cli.command()
def list_collectors():
    """列出所有已注册的采集器"""
    import src.collectors.eastmoney  # noqa: F401
    import src.collectors.ths  # noqa: F401
    import src.collectors.xueqiu  # noqa: F401

    from src.collectors.registry import list_collectors as _list

    collectors = _list()
    for c in collectors:
        console.print(f"  [cyan]{c['name']}[/cyan] - {c['description']}")


if __name__ == "__main__":
    cli()
