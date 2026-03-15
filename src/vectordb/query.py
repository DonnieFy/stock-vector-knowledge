"""向量查询接口"""

import numpy as np
from rich.console import Console
from rich.table import Table

from src.vectordb.embedder import embed, embed_batch, cosine_similarity
from src.vectordb.store import get_collection

console = Console()


def query_similar_text(text: str, top_n: int = 10) -> list[dict]:
    """
    文本相似查询：输入文本，返回最相似的N只股票。

    Args:
        text: 查询文本（如"光伏组件"、"新能源汽车"）
        top_n: 返回数量

    Returns:
        [{code, name, score, document}, ...]
    """
    collection = get_collection()
    query_embedding = embed(text)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_n,
        include=["metadatas", "documents", "distances"],
    )

    items = []
    if results and results["ids"] and results["ids"][0]:
        for i, doc_id in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            distance = results["distances"][0][i] if results["distances"] else 0
            # ChromaDB 默认使用 L2 距离，转换为相似度
            similarity = 1.0 / (1.0 + distance)
            items.append({
                "code": meta.get("stock_code", doc_id),
                "name": meta.get("stock_name", ""),
                "score": round(similarity, 4),
                "distance": round(distance, 4),
            })

    return items


def query_similar_stock(stock_code: str, top_n: int = 10) -> list[dict]:
    """
    股票相似查询：输入股票代码，找到题材最相似的N只股票。

    Args:
        stock_code: 股票代码
        top_n: 返回数量（会多取1个，排除自身）

    Returns:
        [{code, name, score}, ...]
    """
    collection = get_collection()

    # 获取目标股票的向量
    target = collection.get(ids=[stock_code], include=["embeddings"])
    if target["embeddings"] is None or len(target["embeddings"]) == 0:
        console.print(f"[red]未找到股票 {stock_code} 的向量数据[/red]")
        return []

    target_embedding = target["embeddings"][0]

    results = collection.query(
        query_embeddings=[target_embedding],
        n_results=top_n + 1,  # 多取一个排除自身
        include=["metadatas", "distances"],
    )

    items = []
    if results and results["ids"] and results["ids"][0]:
        for i, doc_id in enumerate(results["ids"][0]):
            if doc_id == stock_code:
                continue  # 排除自身
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            distance = results["distances"][0][i] if results["distances"] else 0
            similarity = 1.0 / (1.0 + distance)
            items.append({
                "code": meta.get("stock_code", doc_id),
                "name": meta.get("stock_name", ""),
                "score": round(similarity, 4),
            })

    return items[:top_n]


def cluster_stocks(stock_codes: list[str], n_clusters: int = 3) -> dict:
    """
    拓扑聚类：对N只股票进行聚类分析。

    Args:
        stock_codes: 股票代码列表
        n_clusters: 聚类数量

    Returns:
        {
            clusters: [{cluster_id, stocks: [{code, name}], centroid_text: str}, ...],
            labels: {code: cluster_id},
        }
    """
    from sklearn.cluster import KMeans

    collection = get_collection()

    # 获取所有股票的向量
    target = collection.get(
        ids=stock_codes,
        include=["embeddings", "metadatas"],
    )

    if target["embeddings"] is None or len(target["embeddings"]) == 0:
        console.print("[red]未找到指定股票的向量数据[/red]")
        return {"clusters": [], "labels": {}}

    embeddings = np.array(target["embeddings"])
    ids = target["ids"]
    metadatas = target["metadatas"]

    # 调整聚类数不超过样本数
    actual_clusters = min(n_clusters, len(ids))
    if actual_clusters < 2:
        # 样本太少无法聚类
        return {
            "clusters": [{
                "cluster_id": 0,
                "stocks": [
                    {"code": ids[i], "name": metadatas[i].get("stock_name", "")}
                    for i in range(len(ids))
                ],
            }],
            "labels": {ids[i]: 0 for i in range(len(ids))},
        }

    # KMeans 聚类
    kmeans = KMeans(n_clusters=actual_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(embeddings)

    # 整理结果
    clusters_dict: dict[int, list[dict]] = {}
    labels_map: dict[str, int] = {}

    for i, label in enumerate(labels):
        label = int(label)
        labels_map[ids[i]] = label
        clusters_dict.setdefault(label, []).append({
            "code": ids[i],
            "name": metadatas[i].get("stock_name", ""),
        })

    clusters = []
    for cid in sorted(clusters_dict.keys()):
        # 找离质心最近的股票作为代表
        cluster_indices = [i for i, l in enumerate(labels) if l == cid]
        centroid = kmeans.cluster_centers_[cid]
        distances = [np.linalg.norm(embeddings[i] - centroid) for i in cluster_indices]
        representative_idx = cluster_indices[np.argmin(distances)]

        clusters.append({
            "cluster_id": cid,
            "stocks": clusters_dict[cid],
            "representative": {
                "code": ids[representative_idx],
                "name": metadatas[representative_idx].get("stock_name", ""),
            },
            "size": len(clusters_dict[cid]),
        })

    return {"clusters": clusters, "labels": labels_map}


def print_query_results(results: list[dict], title: str = "查询结果"):
    """格式化打印查询结果"""
    table = Table(title=title)
    table.add_column("排名", style="dim", width=4)
    table.add_column("代码", style="cyan", width=8)
    table.add_column("名称", style="white", width=12)
    table.add_column("相似度", style="green", width=8)

    for i, item in enumerate(results, 1):
        table.add_row(
            str(i),
            item["code"],
            item["name"],
            f"{item['score']:.4f}",
        )

    console.print(table)


def print_cluster_results(result: dict):
    """格式化打印聚类结果"""
    for cluster in result["clusters"]:
        console.print(f"\n[bold cyan]═══ 聚类 {cluster['cluster_id']} ({cluster['size']}只) ═══[/bold cyan]")
        if "representative" in cluster:
            rep = cluster["representative"]
            console.print(f"  [dim]代表股: {rep['code']} {rep['name']}[/dim]")
        for stock in cluster["stocks"]:
            console.print(f"  • {stock['code']} {stock['name']}")


def analyze_themes(stock_codes: list[str], top_n: int = 10, n_clusters: int = 5) -> list[dict]:
    """
    先聚类、再按簇分析语义方向。

    1. 对输入股票做 KMeans 聚类
    2. 对每个簇计算质心向量
    3. 用每个簇的质心去查询 theme_keywords 集合
    4. 返回每个簇的关键词

    Args:
        stock_codes: 股票代码列表
        top_n: 每个簇返回的关键词数量
        n_clusters: 聚类数量（自动取 min(n_clusters, len/3)）

    Returns:
        [{cluster_id, size, stocks: [{code,name}], keywords: [{keyword,score,doc_freq}]}, ...]
    """
    from sklearn.cluster import KMeans
    from src.vectordb.store import get_keywords_collection

    collection = get_collection()

    # 获取输入股票的向量
    target = collection.get(ids=stock_codes, include=["embeddings", "metadatas"])
    if target["embeddings"] is None or len(target["embeddings"]) == 0:
        console.print("[red]未找到指定股票的向量数据[/red]")
        return []

    embeddings = np.array(target["embeddings"])
    ids = target["ids"]
    metadatas = target["metadatas"]

    # 自动确定聚类数
    actual_k = min(n_clusters, max(1, len(ids) // 3))
    if actual_k < 2:
        actual_k = 1

    kw_collection = get_keywords_collection()
    results = []

    if actual_k == 1:
        # 只有一个簇，直接计算质心
        centroid = np.mean(embeddings, axis=0).tolist()
        kw_results = kw_collection.query(
            query_embeddings=[centroid],
            n_results=top_n,
            include=["metadatas", "distances"],
        )
        keywords = _parse_kw_results(kw_results)
        stocks = [
            {"code": ids[i], "name": metadatas[i].get("stock_name", "")}
            for i in range(len(ids))
        ]
        results.append({
            "cluster_id": 0, "size": len(ids),
            "stocks": stocks, "keywords": keywords,
        })
    else:
        # KMeans 聚类
        kmeans = KMeans(n_clusters=actual_k, random_state=42, n_init=10)
        labels = kmeans.fit_predict(embeddings)

        for cid in range(actual_k):
            cluster_indices = [i for i, l in enumerate(labels) if l == cid]
            if not cluster_indices:
                continue

            centroid = kmeans.cluster_centers_[cid].tolist()
            kw_results = kw_collection.query(
                query_embeddings=[centroid],
                n_results=top_n,
                include=["metadatas", "distances"],
            )
            keywords = _parse_kw_results(kw_results)
            stocks = [
                {"code": ids[i], "name": metadatas[i].get("stock_name", "")}
                for i in cluster_indices
            ]
            # 按离质心的距离排序，最近的在前
            results.append({
                "cluster_id": cid, "size": len(cluster_indices),
                "stocks": stocks, "keywords": keywords,
            })

    # 按簇大小降序
    results.sort(key=lambda x: x["size"], reverse=True)
    return results


def _parse_kw_results(kw_results) -> list[dict]:
    """解析 ChromaDB 关键词查询结果"""
    items = []
    if kw_results and kw_results["ids"] and kw_results["ids"][0]:
        for i, kw_id in enumerate(kw_results["ids"][0]):
            meta = kw_results["metadatas"][0][i] if kw_results["metadatas"] else {}
            distance = kw_results["distances"][0][i] if kw_results["distances"] else 0
            similarity = 1.0 / (1.0 + distance)
            items.append({
                "keyword": meta.get("keyword", kw_id),
                "score": round(similarity, 4),
                "doc_freq": meta.get("doc_freq", 0),
            })
    return items


def print_theme_analysis(results: list[dict]):
    """格式化打印主题分析结果（按簇展示）"""
    if not results:
        return

    total = sum(r["size"] for r in results)
    console.print(f"\n[bold cyan]═══ {total} 只股票 → {len(results)} 个语义簇 ═══[/bold cyan]")

    for r in results:
        # 关键词摘要
        kw_str = "、".join(k["keyword"] for k in r["keywords"][:5])
        console.print(f"\n[bold green]▎簇 {r['cluster_id']} ({r['size']}只) → {kw_str}[/bold green]")

        # 成员股票
        stock_names = [f"{s['code']}{s['name']}" for s in r["stocks"]]
        console.print(f"  [dim]成员: {', '.join(stock_names[:8])}{'...' if len(stock_names) > 8 else ''}[/dim]")

        # 关键词表
        table = Table(show_header=True, header_style="dim", box=None, padding=(0, 1))
        table.add_column("关键词", style="white", width=14)
        table.add_column("相似度", style="green", width=8)
        table.add_column("覆盖数", style="cyan", width=6)
        for k in r["keywords"]:
            table.add_row(k["keyword"], f"{k['score']:.4f}", str(k["doc_freq"]))
        console.print(table)
