"""ChromaDB 向量存储管理"""

import math
import re
from collections import defaultdict
from pathlib import Path

import chromadb
from rich.console import Console
from rich.progress import track

from src.config import get_config
from src.vectordb.embedder import embed, embed_batch

console = Console()

COLLECTION_NAME = "stock_themes"
KEYWORDS_COLLECTION_NAME = "theme_keywords"

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
    """获取或创建股票向量集合"""
    global _collection
    if _collection is not None:
        return _collection

    client = _get_client()
    _collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "A股上市公司题材向量库"},
    )
    return _collection


def get_keywords_collection() -> chromadb.Collection:
    """获取或创建关键词向量集合"""
    client = _get_client()
    return client.get_or_create_collection(
        name=KEYWORDS_COLLECTION_NAME,
        metadata={"description": "题材关键词向量库"},
    )


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

    MAX_BATCH = 5000
    for i in range(0, len(ids), MAX_BATCH):
        collection.add(
            ids=ids[i : i + MAX_BATCH],
            embeddings=all_embeddings[i : i + MAX_BATCH],
            metadatas=metadatas[i : i + MAX_BATCH],
            documents=documents[i : i + MAX_BATCH],
        )

    console.print(f"[green]向量库重建完成: {len(docs)} 个文档[/green]")

    # 构建关键词向量集合
    _build_keywords_collection(texts)

    return len(docs)


def _build_keywords_collection(documents: list[str]):
    """
    从文档中提取关键词，计算IDF，嵌入并写入 theme_keywords 集合。
    """
    import jieba
    import jieba.posseg as pseg

    console.print(f"[blue]构建关键词向量集合...[/blue]")

    # 停用词表：过滤常见无意义词（通用商业/金融/描述性词汇）
    stop_words = {
        # 通用企业词
        "公司", "主营", "业务", "产品", "行业", "市场", "技术", "服务", "领域",
        "发展", "应用", "系统", "设备", "生产", "客户", "研发", "解决方案",
        "全球", "国内", "企业", "创新", "平台", "管理", "体系",
        "能力", "价值", "品质", "质量", "单位", "材料", "方案",
        "建设", "投资", "资产", "装备", "工程", "规模", "优势",
        "实现", "提供", "中国", "国家", "区域", "股份", "集团",
        "处理", "数据", "流程", "效率", "成本", "一体化",
        # 金融/股票通用词
        "龙头", "概念", "板块", "题材", "潜力股", "科技股", "成长股",
        "绩优股", "蓝筹股", "白马股", "次新股", "妖股",
        "涨停", "跌停", "复牌", "停牌", "增发", "配股", "回购",
        "上市公司", "控股公司", "股份公司", "子公司",
        # 通用描述/修饰词
        "知名企业", "品牌优势", "品牌价值", "品牌效应",
        "技术实力", "技术优势", "技术壁垒", "核心技术",
        "产业布局", "产业链", "产业集群", "产业升级",
        "主导产品", "主打产品", "拳头产品", "核心产品",
        "竞争优势", "竞争力", "市场份额", "市场地位",
        "盈利能力", "盈利模式", "商业模式", "经营模式",
        "战略布局", "战略规划", "战略合作", "战略投资",
        "公司业绩", "业绩增长", "营业收入", "净利润",
        "性能指标", "性能需求", "机械性能", "电性能",
        "高增值", "高值", "高智能", "高精度", "高效率",
        # 通用技术/管理词
        "物理", "全场景", "数字化", "智能化", "一致性", "冗余",
        "基座", "分发", "链路", "资产保值", "一致性能",
        "数智化", "极精", "极致", "极简", "物性", "表征",
        "无人化", "留证", "演进", "位势", "统治", "赋能",
        "产能", "产量", "项目", "基地", "工厂", "园区",
        "国产", "进口", "出口", "贸易", "销售", "采购",
        "上游", "下游", "终端", "渠道", "供应", "需求",
        "机型", "型号", "产线", "产线", "工艺", "制造",
        # 通用行业归类词（太宽泛）
        "能源行业", "电力行业", "电子行业", "化工行业",
        "制造业", "金融行业", "房地产", "农业",
        "电力企业", "电力公司", "能源供应", "能源需求",
        "能源建设", "能源动力", "能源管理", "能源部", "核能源",
        "能源技术", "能源价格",
        "智能型", "智能工具", "商业智能", "智能机",
        "机电产品",
    }

    # 允许的词性：名词类
    allowed_pos = {"n", "nr", "ns", "nt", "nz", "vn", "an", "eng"}

    total_docs = len(documents)
    # 统计每个词出现在多少篇文档中
    doc_freq = defaultdict(int)

    for doc in documents:
        words_in_doc = set()
        for word, pos in pseg.cut(doc):
            word = word.strip()
            if len(word) < 2:
                continue
            if pos not in allowed_pos:
                continue
            if word in stop_words:
                continue
            words_in_doc.add(word)
        for w in words_in_doc:
            doc_freq[w] += 1

    # IDF过滤：去掉出现在超过50%文档中的词（太通用），以及只出现在1篇中的词（太孤立）
    max_df = total_docs * 0.5
    keywords = {}
    for word, df in doc_freq.items():
        if df < 2 or df > max_df:
            continue
        idf = math.log(total_docs / df)
        keywords[word] = {"doc_freq": df, "idf": round(idf, 4)}

    console.print(f"  [dim]提取到 {len(keywords)} 个有效关键词 (从 {len(doc_freq)} 个候选词中筛选)[/dim]")

    if not keywords:
        console.print("[yellow]未提取到有效关键词[/yellow]")
        return

    # 删除旧的关键词集合
    client = _get_client()
    try:
        client.delete_collection(KEYWORDS_COLLECTION_NAME)
    except Exception:
        pass

    kw_collection = get_keywords_collection()

    # 批量嵌入关键词
    kw_list = list(keywords.keys())
    kw_batch_size = 64
    all_kw_embeddings = []

    for i in range(0, len(kw_list), kw_batch_size):
        batch = kw_list[i : i + kw_batch_size]
        embs = embed_batch(batch)
        all_kw_embeddings.extend(embs)
        console.print(f"  [dim]嵌入关键词 {min(i + kw_batch_size, len(kw_list))}/{len(kw_list)}[/dim]")

    # 写入 ChromaDB
    ids = kw_list
    metadatas = [
        {"keyword": w, "doc_freq": keywords[w]["doc_freq"], "idf": keywords[w]["idf"]}
        for w in kw_list
    ]

    MAX_BATCH = 5000
    for i in range(0, len(ids), MAX_BATCH):
        kw_collection.add(
            ids=ids[i : i + MAX_BATCH],
            embeddings=all_kw_embeddings[i : i + MAX_BATCH],
            metadatas=metadatas[i : i + MAX_BATCH],
        )

    console.print(f"[green]关键词向量集合构建完成: {len(kw_list)} 个关键词[/green]")


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

    ids = [d["code"] for d in new_docs]
    metadatas = [{"stock_code": d["code"], "stock_name": d["name"]} for d in new_docs]
    documents = texts

    MAX_BATCH = 5000
    for i in range(0, len(ids), MAX_BATCH):
        collection.add(
            ids=ids[i : i + MAX_BATCH],
            embeddings=embeddings[i : i + MAX_BATCH],
            metadatas=metadatas[i : i + MAX_BATCH],
            documents=documents[i : i + MAX_BATCH],
        )

    console.print(f"[green]增量更新完成: {len(new_docs)} 个新文档[/green]")
    return len(new_docs)


def get_stats() -> dict:
    """获取向量库统计信息"""
    collection = get_collection()
    count = collection.count()
    try:
        kw_collection = get_keywords_collection()
        kw_count = kw_collection.count()
    except Exception:
        kw_count = 0
    return {
        "collection": COLLECTION_NAME,
        "document_count": count,
        "keywords_count": kw_count,
        "db_path": str(get_config().vectordb_dir),
    }
