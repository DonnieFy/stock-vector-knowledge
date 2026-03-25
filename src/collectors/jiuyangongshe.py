"""韭研公社数据采集器

支持三类数据：
1. 每日异动 (action/field) — 按日期存储
2. 产业异动 (industry/list) — 单文件增量合并
3. 事件时间线 (timeline/list) — 单文件增量合并

数据结构说明见 data/jiuyangongshe/README.md

Usage:
    from src.collectors.jiuyangongshe import fetch_and_save, fetch_range
    from src.collectors.jiuyangongshe import fetch_and_save_industry, fetch_and_save_timeline

    fetch_and_save("2025-01-23")            # 每日异动
    fetch_and_save_industry()               # 产业异动
    fetch_and_save_timeline()               # 事件时间线
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from scrapling import Fetcher
from rich.console import Console

from src.config import get_config

console = Console()

# API 地址
ACTION_FIELD_URL = "https://app.jiuyangongshe.com/jystock-app/api/v1/action/field"
INDUSTRY_LIST_URL = "https://app.jiuyangongshe.com/jystock-app/api/v1/industry/list"
TIMELINE_LIST_URL = "https://app.jiuyangongshe.com/jystock-app/api/v1/timeline/list"

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 3  # 秒


def _build_headers() -> dict:
    """构建带认证信息的请求头"""
    config = get_config()
    return {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "platform": "3",
        "pragma": "no-cache",
        "priority": "u=1, i",
        "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "timestamp": config.jiuyangongshe_timestamp,
        "token": config.jiuyangongshe_token,
        "cookie": config.jiuyangongshe_cookies,
        "Referer": "https://www.jiuyangongshe.com/",
        "Referrer-Policy": "strict-origin-when-cross-origin",
    }


def _ensure_data_dir() -> Path:
    """确保数据存储目录存在"""
    config = get_config()
    action_dir = config.jiuyangongshe_data_dir / "action"
    action_dir.mkdir(parents=True, exist_ok=True)
    return action_dir


def _flatten_stock(stock: dict) -> dict:
    """
    将嵌套的个股数据拉平为一层结构。

    原始数据有 stock -> article -> action_info 三层嵌套，
    提取关键字段到一层 dict 中。
    """
    info = stock.get("article", {}).get("action_info", {})
    return {
        "code": stock.get("code", ""),
        "name": stock.get("name", ""),
        "time": info.get("time") or "",
        "num": info.get("num") or "",
        "day": info.get("day"),
        "edition": info.get("edition"),
        "shares_range": info.get("shares_range"),
        "reason": info.get("reason") or "",
        "expound": info.get("expound") or "",
        "is_crawl": info.get("is_crawl"),
    }


def _transform_response(date_str: str, raw_data: dict) -> dict:
    """
    将 API 原始响应转换为精简存储结构。

    返回:
        {
            "date": "2025-01-23",
            "collected_at": "...",
            "fields": [
                {
                    "name": "板块名称",
                    "reason": "驱动事件",
                    "stocks": [ {扁平化个股数据}, ... ]
                },
                ...
            ]
        }
    """
    fields = []
    for field in raw_data.get("data", []):
        if not isinstance(field, dict):
            continue

        # 跳过简图（无个股数据）
        stock_list = field.get("list", [])
        if not stock_list and field.get("count", 0) == 0:
            continue

        flat_stocks = [_flatten_stock(s) for s in stock_list]

        fields.append({
            "name": field.get("name", ""),
            "reason": field.get("reason", ""),
            "stocks": flat_stocks,
        })

    return {
        "date": date_str,
        "collected_at": datetime.now().isoformat(),
        "fields": fields,
    }


def _login() -> bool:
    """
    使用配置的账号密码登录，获取新 token 并更新配置。
    使用 Scrapling 完整模拟浏览器绕过防护
    """
    config = get_config()
    phone = config.jiuyangongshe_phone
    password = config.jiuyangongshe_password
    
    if not phone or not password:
        console.print("[yellow]  未配置韭研公社账号密码(phone/password)，无法自动登录。[/yellow]")
        return False
        
    console.print(f"[dim]  通过 Scrapling 模拟浏览器自动登录 ({phone})...[/dim]")
    
    try:
        from scrapling.fetchers import StealthySession
        tokens = {}
        
        def on_response(response):
            # 监听接口获取凭证
            if "user/login" in response.url or "token" in response.url:
                try:
                    data = response.json()
                    if data and isinstance(data, dict) and "data" in data and "sessionToken" in data["data"]:
                        tokens["token"] = data["data"]["sessionToken"]
                except:
                    pass

        def page_action(page):
            page.on("response", on_response)
            page.locator('.user-box .name').first.click()
            page.wait_for_timeout(2000)
            
            # 切换到密码登录
            try:
                page.locator('#tab-accounts').click(timeout=3000)
            except:
                pass
                
            page.locator('input[name="phone"]').last.fill(phone)
            page.locator('input[name="password"]').fill(password)
            
            # 点击弹窗内的登录按钮
            login_btns = page.get_by_text("登录", exact=True)
            if login_btns.count() > 1:
                login_btns.last.click()
            else:
                login_btns.click()
                
            page.wait_for_timeout(4000)
            
            # 提取 cookies
            cookies = page.context.cookies()
            cookie_str = "; ".join([f'{c["name"]}={c["value"]}' for c in cookies])
            tokens["cookies"] = cookie_str

        with StealthySession(headless=True) as session:
            session.fetch("https://www.jiuyangongshe.com/", page_action=page_action)
            
        if "token" in tokens:
            import time
            new_timestamp = str(int(time.time() * 1000))
            config.update_jiuyangongshe_auth(
                token=tokens["token"],
                timestamp=new_timestamp,
                cookies=tokens.get("cookies", "")
            )
            console.print("[green]  自动登录成功，已保存新 Token。[/green]")
            return True
        else:
            console.print("[yellow]  自动登录失败：未能从网络拦截中获取到 sessionToken。可能是由于验证码或网站更新。[/yellow]")
            return False
            
    except Exception as e:
        console.print(f"[red]  自动登录异常: {e}[/red]")
        return False


def fetch_action_data(date_str: str, auto_login: bool = True) -> dict | None:
    """
    获取指定日期的异动数据（原始 API 响应）。
    如果 token 失效或没数据，会自动尝试登录一次。

    Args:
        date_str: 日期字符串，格式为 YYYY-MM-DD
        auto_login: 当失败时是否尝试自动登录（防止死循环）

    Returns:
        API 返回的 JSON 数据，失败返回 None
    """
    headers = _build_headers()
    body = {"date": date_str, "pc": 1}

    for attempt in range(MAX_RETRIES):
        try:
            response = Fetcher.post(
                ACTION_FIELD_URL,
                headers=headers,
                json=body,
                timeout=15,
            )
            if response.status == 200:
                result = response.json() if hasattr(response, 'json') else json.loads(response.body)
                
                # 检查是否因为 Token 过期导致异常 (如要求重新登录)
                err_code = str(result.get("errCode", ""))
                
                if result.get("data") is not None and str(result.get("data")) != "[]":
                    return result
                elif err_code == "401" or err_code == "10000" or result.get("data") is None:
                    # Token 可能无效或过期
                    console.print(f"[yellow]  API 未返回数据或凭证失效: {result.get('msg', '未知错误')} (errCode: {err_code})[/yellow]")
                    
                    if auto_login:
                        if _login():
                            # 登录成功，重新构建 headers 递归重试（不带 auto_login）
                            return fetch_action_data(date_str, auto_login=False)
                    
                    return result
                else:
                    return result
            else:
                console.print(
                    f"[yellow]  HTTP {response.status}，"
                    f"等待 {RETRY_DELAY}s 重试 ({attempt + 1}/{MAX_RETRIES})...[/yellow]"
                )
                time.sleep(RETRY_DELAY)
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                console.print(
                    f"[yellow]  请求失败({e})，"
                    f"{RETRY_DELAY}s 后重试 ({attempt + 1}/{MAX_RETRIES})...[/yellow]"
                )
                time.sleep(RETRY_DELAY)
            else:
                console.print(f"[red]  请求最终失败: {e}[/red]")

    return None


def save_action_data(date_str: str, raw_data: dict) -> Path | None:
    """
    将异动数据转换为精简格式并保存为 JSON 文件。

    Args:
        date_str: 日期字符串
        raw_data: API 返回的原始数据

    Returns:
        保存的文件路径, 无数据则不保存并返回 None
    """
    action_dir = _ensure_data_dir()
    file_path = action_dir / f"{date_str}.json"

    save_data = _transform_response(date_str, raw_data)
    
    if not save_data["fields"]:
        return None

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)

    return file_path


def fetch_and_save(date_str: str) -> bool:
    """
    采集并保存指定日期的异动数据。

    Args:
        date_str: 日期字符串

    Returns:
        是否成功
    """
    console.print(f"  采集 {date_str} ...", end=" ")
    raw_data = fetch_action_data(date_str)

    if raw_data is None:
        console.print("[red]失败[/red]")
        return False

    # 统计
    transformed = _transform_response(date_str, raw_data)
    fields = transformed["fields"]
    
    if not fields:
        console.print("[dim]无数据(如节假日或未产生异动)，忽略[/dim]")
        return True

    file_path = save_action_data(date_str, raw_data)

    total_stocks = sum(len(f["stocks"]) for f in fields)
    field_names = [f["name"] for f in fields if f["name"]]

    console.print(
        f"[green]✓[/green] {len(fields)} 个板块, {total_stocks} 只个股"
        f" [{', '.join(field_names[:5])}{'...' if len(field_names) > 5 else ''}]"
    )

    return True


def fetch_range(start_date: str, end_date: str, interval: float = 1.0) -> dict:
    """
    批量采集日期范围内的异动数据。

    Args:
        start_date: 起始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        interval: 请求间隔 (秒)

    Returns:
        {"success": [...], "failed": [...]}
    """
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    if start > end:
        start, end = end, start

    results = {"success": [], "failed": []}
    current = start

    console.print(
        f"[bold blue]【韭研公社】批量采集异动数据: {start_date} → {end_date}[/bold blue]"
    )

    while current <= end:
        date_str = current.strftime("%Y-%m-%d")

        # 跳过已存在的文件
        action_dir = _ensure_data_dir()
        if (action_dir / f"{date_str}.json").exists():
            console.print(f"  {date_str} [dim]已存在，跳过[/dim]")
            results["success"].append(date_str)
            current += timedelta(days=1)
            continue

        ok = fetch_and_save(date_str)
        if ok:
            results["success"].append(date_str)
        else:
            results["failed"].append(date_str)

        current += timedelta(days=1)

        if current <= end:
            time.sleep(interval)

    console.print(
        f"[bold green]采集完成: 成功 {len(results['success'])}, "
        f"失败 {len(results['failed'])}[/bold green]"
    )

    return results


# ══════════════════════════════════════════════════════
# 产业异动 (industry/list)
# ══════════════════════════════════════════════════════


def _flatten_industry(item: dict) -> dict:
    """提取产业异动的关键字段。"""
    return {
        "industry_id": item.get("industry_id", ""),
        "title": item.get("title", ""),
        "keyword": item.get("keyword", ""),
        "content": item.get("content", ""),
        "create_time": item.get("create_time", ""),
        "update_time": item.get("update_time", ""),
        "browsers_count": item.get("browsers_count", 0),
    }


def fetch_industry_list() -> list[dict]:
    """
    分页拉取全部产业异动数据。

    Returns:
        精简后的产业列表
    """
    headers = _build_headers()
    all_items = []
    page = 1
    page_size = 50

    while True:
        body = {"start": page, "limit": page_size}
        try:
            resp = Fetcher.post(
                INDUSTRY_LIST_URL, headers=headers, json=body, timeout=15
            )
            if resp.status != 200:
                console.print(f"[yellow]  industry HTTP {resp.status}[/yellow]")
                break

            data = resp.json() if hasattr(resp, 'json') else json.loads(resp.body)
            if data.get("errCode") != "0" and str(data.get("errCode")) != "0":
                console.print(f"[yellow]  industry API 错误: {data.get('msg', '')}[/yellow]")
                break

            page_data = data.get("data", {})
            results = page_data.get("result", [])
            for item in results:
                all_items.append(_flatten_industry(item))

            if not page_data.get("hasNext", False):
                break

            page += 1
            time.sleep(0.5)

        except Exception as e:
            console.print(f"[red]  industry 请求失败: {e}[/red]")
            break

    return all_items


def save_industry_data(new_items: list[dict]) -> Path:
    """
    增量合并产业数据并保存。

    以 industry_id 去重，update_time 更新时覆盖旧记录。

    Returns:
        保存的文件路径
    """
    config = get_config()
    data_dir = config.jiuyangongshe_data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    file_path = data_dir / "industry.json"

    # 加载已有数据
    existing = {}
    if file_path.exists():
        with open(file_path, "r", encoding="utf-8") as f:
            saved = json.load(f)
            for item in saved.get("items", []):
                existing[item["industry_id"]] = item

    # 合并
    added = 0
    updated = 0
    for item in new_items:
        iid = item["industry_id"]
        if iid in existing:
            if item.get("update_time", "") > existing[iid].get("update_time", ""):
                existing[iid] = item
                updated += 1
        else:
            existing[iid] = item
            added += 1

    # 按 update_time 降序排列
    merged = sorted(existing.values(), key=lambda x: x.get("update_time", ""), reverse=True)

    save_data = {
        "collected_at": datetime.now().isoformat(),
        "total": len(merged),
        "items": merged,
    }

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)

    console.print(
        f"[green]  产业数据已保存: {len(merged)} 条 "
        f"(新增 {added}, 更新 {updated})[/green]"
    )
    return file_path


def fetch_and_save_industry() -> bool:
    """采集并保存产业异动数据。"""
    console.print("[bold blue]【韭研公社】采集产业异动数据...[/bold blue]")
    items = fetch_industry_list()
    if not items:
        console.print("[yellow]  未获取到产业数据[/yellow]")
        return False

    console.print(f"  拉取到 {len(items)} 条产业记录")
    save_industry_data(items)
    return True


# ══════════════════════════════════════════════════════
# 事件时间线 (timeline/list)
# ══════════════════════════════════════════════════════


def _flatten_timeline_event(event: dict) -> dict:
    """提取时间线事件的关键字段。"""
    timeline = event.get("timeline", {})
    themes = [
        t.get("name", "") for t in timeline.get("theme_list", []) if t.get("name")
    ]
    return {
        "article_id": event.get("article_id", ""),
        "date": timeline.get("date", ""),
        "title": event.get("title", ""),
        "content": event.get("content", ""),
        "grade": timeline.get("grade"),
        "themes": themes,
        "create_time": timeline.get("create_time", ""),
    }


def fetch_timeline_list() -> list[dict]:
    """
    拉取事件时间线数据（默认返回约1个月范围）。

    Returns:
        精简后的事件列表
    """
    headers = _build_headers()
    all_events = []

    try:
        resp = Fetcher.post(
            TIMELINE_LIST_URL, headers=headers, json={}, timeout=15
        )
        if resp.status != 200:
            console.print(f"[yellow]  timeline HTTP {resp.status}[/yellow]")
            return []

        data = resp.json() if hasattr(resp, 'json') else json.loads(resp.body)
        if data.get("errCode") != "0" and str(data.get("errCode")) != "0":
            console.print(f"[yellow]  timeline API 错误: {data.get('msg', '')}[/yellow]")
            return []

        groups = data.get("data", [])
        for group in groups:
            for event in group.get("list", []):
                all_events.append(_flatten_timeline_event(event))

    except Exception as e:
        console.print(f"[red]  timeline 请求失败: {e}[/red]")

    return all_events


def save_timeline_data(new_events: list[dict]) -> Path:
    """
    增量合并时间线数据并保存。

    以 article_id 去重，已存在的不覆盖。

    Returns:
        保存的文件路径
    """
    config = get_config()
    data_dir = config.jiuyangongshe_data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    file_path = data_dir / "timeline.json"

    # 加载已有数据
    existing = {}
    if file_path.exists():
        with open(file_path, "r", encoding="utf-8") as f:
            saved = json.load(f)
            for item in saved.get("items", []):
                existing[item["article_id"]] = item

    # 合并
    added = 0
    for event in new_events:
        aid = event["article_id"]
        if aid not in existing:
            existing[aid] = event
            added += 1

    # 按日期排序
    merged = sorted(existing.values(), key=lambda x: x.get("date", ""))

    save_data = {
        "collected_at": datetime.now().isoformat(),
        "total": len(merged),
        "items": merged,
    }

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)

    console.print(
        f"[green]  时间线数据已保存: {len(merged)} 条 "
        f"(新增 {added})[/green]"
    )
    return file_path


def fetch_and_save_timeline() -> bool:
    """采集并保存事件时间线数据。"""
    console.print("[bold blue]【韭研公社】采集事件时间线...[/bold blue]")
    events = fetch_timeline_list()
    if not events:
        console.print("[yellow]  未获取到时间线数据[/yellow]")
        return False

    # 统计日期范围
    dates = sorted(set(e["date"] for e in events if e.get("date")))
    console.print(f"  拉取到 {len(events)} 个事件 ({dates[0]} ~ {dates[-1]})")
    save_timeline_data(events)
    return True


def fetch_recent_30_days():
    """拉取近30天的异动数据"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    
    fetch_range(start_str, end_str)


if __name__ == "__main__":
    fetch_recent_30_days()
