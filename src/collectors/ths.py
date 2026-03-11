"""同花顺数据采集器 - 基于 10jqka 网页爬取"""

import re
import time
import requests
from rich.console import Console
from rich.progress import track

from src.collectors.base import BaseCollector
from src.collectors.registry import register_collector

console = Console()

# 请求头，模拟浏览器访问
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 3  # 秒


def _request_with_retry(url: str, timeout: int = 15) -> requests.Response | None:
    """带重试的 HTTP GET 请求"""
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(url, headers=_HEADERS, timeout=timeout)
            r.encoding = "gbk"
            if r.status_code == 200:
                return r
            if r.status_code == 403:
                # 被反爬限制，等待更久
                console.print(f"[yellow]  请求被限制(403)，等待 {RETRY_DELAY * 2}s 重试...[/yellow]")
                time.sleep(RETRY_DELAY * 2)
                continue
        except requests.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                console.print(f"[yellow]  请求失败({e})，{RETRY_DELAY}s 后重试...[/yellow]")
                time.sleep(RETRY_DELAY)
    return None


def _parse_stock_concepts(html: str) -> list[dict]:
    """
    从同花顺个股概念页面 HTML 解析概念列表。

    页面结构: gnContent 区域中每个概念由两个 <tr> 行组成:
    1. 普通行: 包含 gnName(概念名称) 和 tdContent(截断摘要)
    2. extend_content 行: 包含概念解析的完整描述

    本方法从 extend_content 行提取完整描述，避免截断问题。

    Returns:
        [{"name": "概念名称", "description": "完整概念解析"}, ...]
    """
    concepts = []

    # 找到 gnContent 区域
    content_match = re.search(
        r'class="gnContent"[^>]*>(.*)',
        html,
        re.DOTALL,
    )
    if not content_match:
        return concepts

    content = content_match.group(1)

    # 按 <tr> 拆分行，保留 tag 属性以区分普通行和 extend_content 行
    tr_pattern = re.compile(r'<tr\s*([^>]*)>', re.DOTALL)
    parts = tr_pattern.split(content)

    # parts 结构: [前置内容, attrs1, content1, attrs2, content2, ...]
    current_name = None
    current_truncated_desc = None

    for i in range(1, len(parts), 2):
        attrs = parts[i].strip()
        block = parts[i + 1] if i + 1 < len(parts) else ""

        is_extend = 'extend_content' in attrs

        if not is_extend:
            # 普通行 - 提取概念名称
            name_match = re.search(
                r'class="gnName[^"]*"[^>]*>(.*?)(?:</td|</div|</span)',
                block,
                re.DOTALL,
            )
            if not name_match:
                continue
            name = re.sub(r'<[^>]+>', '', name_match.group(1)).strip()
            if not name:
                continue

            current_name = name

            # 提取截断摘要作为后备
            current_truncated_desc = ""
            desc_match = re.search(
                r'class="tdContent"[^>]*>(.*?)(?:</div)',
                block,
                re.DOTALL,
            )
            if desc_match:
                desc = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip()
                current_truncated_desc = desc.replace('\xa0', ' ').replace('&nbsp;', ' ').strip()
        else:
            # extend_content 行 - 提取完整描述
            if current_name is None:
                continue

            desc = _extract_extend_content_text(block)
            if not desc:
                desc = current_truncated_desc or ""

            concepts.append({"name": current_name, "description": desc})
            current_name = None
            current_truncated_desc = None

    # 处理最后一个没有 extend_content 行的概念(极端情况)
    if current_name is not None:
        concepts.append({"name": current_name, "description": current_truncated_desc or ""})

    return concepts


def _extract_extend_content_text(block: str) -> str:
    """从 extend_content 行的 HTML 块中提取纯文本描述"""
    # 优先从 scrollbar-macosx div 中提取
    scroll_match = re.search(
        r'class="scrollbar-macosx[^"]*"[^>]*>(.*?)</div>\s*</td>',
        block,
        re.DOTALL,
    )
    if scroll_match:
        inner = scroll_match.group(1)
        # 移除 bg_trigon_box 装饰元素
        inner = re.sub(r'<div[^>]*class="bg_trigon_box"[^>]*></div>', '', inner)
        text = re.sub(r'<[^>]+>', '', inner).strip()
    else:
        text = re.sub(r'<[^>]+>', '', block).strip()

    text = text.replace('\xa0', ' ').replace('&nbsp;', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _parse_stock_industry(html: str) -> str:
    """从同花顺个股概念页面解析行业分类"""
    # 尝试从概念页面获取行业信息
    industry_match = re.search(
        r'所属行业.*?<a[^>]*href="[^"]*"[^>]*>([^<]+)</a>',
        html,
        re.DOTALL,
    )
    if industry_match:
        industry = industry_match.group(1).strip()
        if industry and industry != "更多>>":
            return industry
    return ""


@register_collector
class THSCollector(BaseCollector):
    """
    同花顺数据采集器。

    通过爬取 basic.10jqka.com.cn 获取每只股票的概念板块和行业信息。
    """

    name = "ths"
    description = "同花顺概念板块采集（基于 10jqka 网页）"

    def collect_full(self, stocks: list[dict], limit: int | None = None) -> None:
        """全量采集：逐股获取概念板块数据"""
        console.print("[bold blue]【同花顺】开始全量采集...[/bold blue]")

        target_stocks = stocks[:limit] if limit else stocks
        success_count = 0
        error_count = 0
        empty_count = 0

        for stock in track(target_stocks, description="[同花顺] 采集个股概念"):
            code = stock["code"]
            try:
                data = self._collect_stock_concepts(code, stock["name"])
                self.save_draft(code, data)
                if data.get("concepts_ths"):
                    success_count += 1
                else:
                    empty_count += 1
            except Exception as e:
                console.print(f"[yellow]  跳过 {code} {stock['name']}: {e}[/yellow]")
                error_count += 1

            self.sleep()

        console.print(
            f"[green]【同花顺】全量采集完成: "
            f"有概念 {success_count}, 概念为空 {empty_count}, 失败 {error_count}[/green]"
        )

    def collect_incremental(self, stocks: list[dict]) -> None:
        """增量采集：仅采集尚未采集的股票"""
        console.print("[bold blue]【同花顺】开始增量采集...[/bold blue]")

        new_stocks = [s for s in stocks if not self.has_draft(s["code"])]
        if not new_stocks:
            console.print("[dim]【同花顺】无新增股票需要采集[/dim]")
            return

        console.print(f"[blue]发现 {len(new_stocks)} 只新股票[/blue]")
        self.collect_full(new_stocks)

    def _collect_stock_concepts(self, code: str, name: str) -> dict:
        """
        采集单只股票的概念板块数据。

        通过访问 basic.10jqka.com.cn/{code}/concept.html 获取。
        """
        url = f"https://basic.10jqka.com.cn/{code}/concept.html"
        r = _request_with_retry(url)

        data = {
            "code": code,
            "name": name,
            "concepts_ths": [],
            "industry": "",
        }

        if r is None:
            return data

        html = r.text

        # 解析概念列表
        concepts = _parse_stock_concepts(html)
        data["concepts_ths"] = concepts

        # 解析行业信息
        industry = _parse_stock_industry(html)
        data["industry"] = industry

        return data
