"""DashScope Embedding 封装，使用 DashScope 原生 API（非 OpenAI 兼容模式）。

因为 DashScope OpenAI 兼容模式不支持 embedding 端点，
所以直接调用原生 API：https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding
"""
import os
import logging
import requests
from typing import List
from langchain_core.embeddings import Embeddings
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class DashScopeEmbeddings(BaseModel, Embeddings):
    """DashScope 文本向量模型，调用原生 API。"""

    model: str = "text-embedding-v2"
    api_key: str = ""
    base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    timeout: int = 30

    def _get_headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of documents using DashScope native API."""
        if not texts:
            return []

        url = f"{self.base_url}/services/embeddings/text-embedding/text-embedding"
        payload = {
            "model": self.model,
            "input": {
                "texts": texts,
            },
            "parameters": {
                "text_type": "document",
            },
        }

        try:
            resp = requests.post(
                url,
                headers=self._get_headers(),
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            # DashScope 原生返回格式: {"output": {"embeddings": [{"text_index": 0, "embedding": [...]}, ...]}}
            embeddings_raw = data["output"]["embeddings"]
            # 按 text_index 排序确保顺序正确
            embeddings_raw.sort(key=lambda x: x["text_index"])
            embeddings = [item["embedding"] for item in embeddings_raw]
            logger.debug(f"[DashScopeEmbeddings] embedded {len(texts)} docs, dim={len(embeddings[0]) if embeddings else 0}")
            return embeddings
        except Exception as e:
            logger.error(f"[DashScopeEmbeddings] embed_documents failed: {e}")
            raise

    def embed_query(self, text: str) -> List[float]:
        """Embed a single query."""
        if not text:
            return []

        url = f"{self.base_url}/services/embeddings/text-embedding/text-embedding"
        payload = {
            "model": self.model,
            "input": {
                "texts": [text],
            },
            "parameters": {
                "text_type": "query",
            },
        }

        try:
            resp = requests.post(
                url,
                headers=self._get_headers(),
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            embeddings_raw = data["output"]["embeddings"]
            return embeddings_raw[0]["embedding"]
        except Exception as e:
            logger.error(f"[DashScopeEmbeddings] embed_query failed: {e}")
            raise


def get_embedding_function() -> DashScopeEmbeddings:
    """获取 Embedding 实例，配置从 .env 读取。"""
    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    base_url = os.getenv("DASHSCOPE_EMBEDDING_URL", "https://dashscope.aliyuncs.com/api/v1")
    model = os.getenv("EMBEDDING_MODEL", "text-embedding-v2")

    return DashScopeEmbeddings(
        model=model,
        api_key=api_key,
        base_url=base_url,
    )
