"""ChromaDB 向量存储管理"""

import re
from pathlib import Path

import chromadb
from rich.console import Console
from rich.progress import track

from src.config import get_config
from src.vectordb.embedder import embed, embed_batch

console = Console()

COLLECTION_NAME = "stock_themes"

_client: chromadb.ClientAPI | None = None
_collection: chromadb.Collection | None = None


def _get_client() -> chromadb.ClientAPI:
    """获取 ChromaDB 客户端"""
    global _client
    if _client is not None:
        return _client

    config = get_config()
    db_path = config.vectordb_dir
    db_path.mkdir(parents=True, exist_ok=True)

    _client = chromadb.PersistentClient(path=str(db_path))
    return _client


def get_collection() -> chromadb.Collection:
    """获取或创建向量集合"""
    global _collection
    if _collection is not None:
        return _collection

    client = _get_client()
    _collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "A股上市公司题材向量库"},
    )
    return _collection


def _parse_summary(file_path: Path) -> dict | None:
    """
    解析摘要MD文件，提取结构化数据。

    Returns:
        {code, name, content, sections} 或 None
    """
    content = file_path.read_text(encoding="utf-8").strip()
    if not content:
        return None

    # 从文件名提取代码和名称
    stem = file_path.stem  # 例如 "000001_平安银行"
    parts = stem.split("_", 1)
    code = parts[0] if parts else ""
    name = parts[1] if len(parts) > 1 else ""

    # 如果文件名没有代码信息，尝试从内容标题提取
    if not code:
        match = re.search(r"^#\s+(\d{6})\s+(.+)", content, re.MULTILINE)
        if match:
            code = match.group(1)
            name = match.group(2).strip()

    if not code:
        return None

    return {
        "code": code,
        "name": name,
        "content": content,
    }


def vectorize_rebuild() -> int:
    """
    全量重建向量库。

    读取所有摘要文件 → 嵌入 → 写入 ChromaDB。

    Returns:
        写入的文档数量
    """
    config = get_config()
    summaries_dir = config.summaries_dir

    if not summaries_dir.exists():
        console.print("[yellow]摘要目录不存在，请先生成摘要[/yellow]")
        return 0

    md_files = sorted(summaries_dir.glob("*.md"))
    if not md_files:
        console.print("[yellow]摘要目录为空[/yellow]")
        return 0

    # 重建：先删除旧集合
    client = _get_client()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    global _collection
    _collection = None
    collection = get_collection()

    # 解析所有摘要
    docs = []
    for f in md_files:
        parsed = _parse_summary(f)
        if parsed:
            docs.append(parsed)

    if not docs:
        console.print("[yellow]没有有效的摘要文件[/yellow]")
        return 0

    console.print(f"[blue]向量化 {len(docs)} 个摘要文件...[/blue]")

    # 批量嵌入
    texts = [d["content"] for d in docs]
    batch_size = 32
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        embeddings = embed_batch(batch)
        all_embeddings.extend(embeddings)
        console.print(f"  [dim]已嵌入 {min(i + batch_size, len(texts))}/{len(texts)}[/dim]")

    # 写入 ChromaDB
    ids = [d["code"] for d in docs]
    metadatas = [{"stock_code": d["code"], "stock_name": d["name"]} for d in docs]
    documents = texts

    collection.add(
        ids=ids,
        embeddings=all_embeddings,
        metadatas=metadatas,
        documents=documents,
    )

    console.print(f"[green]向量库重建完成: {len(docs)} 个文档[/green]")
    return len(docs)


def vectorize_update() -> int:
    """
    增量更新向量库。

    仅处理新增或更新的摘要文件。

    Returns:
        新增/更新的文档数量
    """
    config = get_config()
    summaries_dir = config.summaries_dir
    collection = get_collection()

    md_files = sorted(summaries_dir.glob("*.md"))
    if not md_files:
        return 0

    # 获取已有文档
    existing = collection.get()
    existing_ids = set(existing["ids"]) if existing["ids"] else set()

    new_docs = []
    for f in md_files:
        parsed = _parse_summary(f)
        if parsed and parsed["code"] not in existing_ids:
            new_docs.append(parsed)

    if not new_docs:
        console.print("[dim]无新增文档需要向量化[/dim]")
        return 0

    console.print(f"[blue]增量向量化 {len(new_docs)} 个新文档...[/blue]")

    texts = [d["content"] for d in new_docs]
    embeddings = embed_batch(texts)

    collection.add(
        ids=[d["code"] for d in new_docs],
        embeddings=embeddings,
        metadatas=[{"stock_code": d["code"], "stock_name": d["name"]} for d in new_docs],
        documents=texts,
    )

    console.print(f"[green]增量更新完成: {len(new_docs)} 个新文档[/green]")
    return len(new_docs)


def get_stats() -> dict:
    """获取向量库统计信息"""
    collection = get_collection()
    count = collection.count()
    return {
        "collection": COLLECTION_NAME,
        "document_count": count,
        "db_path": str(get_config().vectordb_dir),
    }
