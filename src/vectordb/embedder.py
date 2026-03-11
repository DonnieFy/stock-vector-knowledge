"""嵌入模型管理"""

from typing import Any

import numpy as np
from rich.console import Console

from src.config import get_config

console = Console()

_model: Any = None


def _load_model():
    """懒加载嵌入模型"""
    global _model
    if _model is not None:
        return _model

    config = get_config()
    model_name = config.embedding_model
    device = config.embedding_device

    console.print(f"[blue]加载嵌入模型: {model_name} (device={device})...[/blue]")

    from sentence_transformers import SentenceTransformer

    _model = SentenceTransformer(model_name, device=device)
    console.print(f"[green]模型加载完成 (维度={_model.get_sentence_embedding_dimension()})[/green]")
    return _model


def embed(text: str) -> list[float]:
    """
    对单条文本进行向量化。

    Args:
        text: 输入文本

    Returns:
        嵌入向量（float列表）
    """
    model = _load_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


def embed_batch(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """
    批量向量化。

    Args:
        texts: 文本列表
        batch_size: 批大小

    Returns:
        嵌入向量列表
    """
    model = _load_model()
    vectors = model.encode(texts, batch_size=batch_size, normalize_embeddings=True)
    return vectors.tolist()


def get_dimension() -> int:
    """获取嵌入向量维度"""
    model = _load_model()
    return model.get_sentence_embedding_dimension()


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """计算余弦相似度"""
    a = np.array(vec_a)
    b = np.array(vec_b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))
