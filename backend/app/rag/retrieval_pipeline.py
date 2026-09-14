"""检索层 Pipeline：Dedup + RRF Fusion + Ingredient-aware Rerank。

流程：
    RAG candidates (通过 threshold)
    + Tavily results
        ↓
    Deduplication (URL / title)
        ↓
    RRF Fusion (rank-based, RRF_K=60)
        ↓
    Ingredient Match Score
        ↓
    Final Score = 0.5 * normalized_rrf + 0.5 * ingredient_match
        ↓
    Sort DESC → Top-K
"""
import hashlib
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from app.rag.retriever import (
    INGREDIENT_ALIASES,
    _extract_recipe_ingredients,
    _normalize_ingredient,
)

logger = logging.getLogger(__name__)

RRF_K = 60
DEFAULT_FINAL_TOP_K = 3

DEFAULT_RRF_WEIGHT = 0.5
DEFAULT_INGREDIENT_WEIGHT = 0.5


@dataclass
class RetrievalCandidate:
    """统一检索候选数据结构。"""
    id: str
    title: str
    content: str
    source: str  # "rag" | "tavily"

    url: Optional[str] = None
    semantic_score: Optional[float] = None

    rag_rank: Optional[int] = None
    tavily_rank: Optional[int] = None

    rrf_score: float = 0.0
    ingredient_match_score: float = 0.0
    final_score: float = 0.0

    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """转换为与 RecipeAgent 兼容的 dict 格式。"""
        return {
            "title": self.title,
            "content": self.content,
            "source": self.source,
            "url": self.url or "",
            "score": self.semantic_score or 0.0,
            "ingredient_match_score": self.ingredient_match_score,
            "rrf_score": self.rrf_score,
            "rerank_score": self.final_score,
            "metadata": self.metadata,
        }


def _normalize_title(title: str) -> str:
    """标题标准化：去空格、转小写。"""
    return re.sub(r"\s+", "", title).lower()


def _make_id(title: str, url: str = "", source: str = "") -> str:
    """生成候选 ID。URL 相同时 ID 相同（用于跨源去重）；URL 为空时加 source 区分。"""
    if url:
        raw = f"{_normalize_title(title)}|{url}"
    else:
        raw = f"{_normalize_title(title)}|{source}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def _get_final_weights() -> tuple[float, float]:
    """读取最终 rerank 权重。"""
    try:
        rw = float(os.getenv("RRF_FINAL_WEIGHT", str(DEFAULT_RRF_WEIGHT)))
    except ValueError:
        rw = DEFAULT_RRF_WEIGHT
    try:
        iw = float(os.getenv("RRF_INGREDIENT_WEIGHT", str(DEFAULT_INGREDIENT_WEIGHT)))
    except ValueError:
        iw = DEFAULT_INGREDIENT_WEIGHT

    total = rw + iw
    if abs(total - 1.0) > 0.05:
        logger.warning(
            f"[Pipeline] final weights sum={total:.2f}, expected ~1.0, using defaults"
        )
        return DEFAULT_RRF_WEIGHT, DEFAULT_INGREDIENT_WEIGHT
    return rw, iw


def deduplicate(
    rag_candidates: list[dict],
    tavily_candidates: list[dict],
) -> list[RetrievalCandidate]:
    """去重：URL 优先，其次标题标准化匹配。

    RAG 和 Tavily 的同名菜谱如果内容不同，保留两个候选。
    """
    by_id: dict[str, RetrievalCandidate] = {}
    title_to_ids: dict[str, set[str]] = {}

    # RAG 结果（已经通过 threshold）
    for item in rag_candidates:
        title = item.get("title", "").strip()
        url = item.get("url", "")
        cid = _make_id(title, url, "rag")
        url_key = url.strip().lower() if url else None

        # 检查 URL 去重
        if url_key:
            existing = next(
                (c for c in by_id.values()
                 if c.url and c.url.strip().lower() == url_key),
                None,
            )
            if existing:
                logger.info(f"[Pipeline] RAG dedup by URL: {title} → merge with {existing.title}")
                existing.rag_rank = None
                continue

        cand = RetrievalCandidate(
            id=cid,
            title=title,
            content=item.get("content", ""),
            source="rag",
            url=url,
            semantic_score=item.get("score"),
            metadata=item.get("metadata", {}),
        )
        by_id[cid] = cand

        norm_title = _normalize_title(title)
        if norm_title:
            title_to_ids.setdefault(norm_title, set()).add(cid)

    # Tavily 结果
    for item in tavily_candidates:
        title = item.get("title", "").strip()
        url = item.get("url", "")
        cid = _make_id(title, url, "tavily")
        url_key = url.strip().lower() if url else None

        # URL 去重
        if url_key:
            existing = next(
                (c for c in by_id.values()
                 if c.url and c.url.strip().lower() == url_key),
                None,
            )
            if existing:
                logger.info(f"[Pipeline] Tavily dedup by URL: {title} → merge with {existing.title}")
                continue

        # 标题去重：只对 RAG 和 Tavily 之间做标题去重
        norm_title = _normalize_title(title)
        if norm_title and norm_title in title_to_ids:
            rag_ids = title_to_ids[norm_title]
            # 检查内容是否高度相似（简单前 200 字符比较）
            tavily_content = item.get("content", "")[:200]
            for rid in rag_ids:
                rag_cand = by_id.get(rid)
                if rag_cand and rag_cand.content[:200] == tavily_content:
                    logger.info(f"[Pipeline] Tavily dedup by title+content: {title}")
                    cid = None
                    break
            else:
                # 标题相同但内容不同 → 保留为独立候选
                logger.info(f"[Pipeline] Same title, different content, keeping both: {title}")
                cid = _make_id(title, url, "tavily")
            if cid is None:
                continue

        cand = RetrievalCandidate(
            id=cid,
            title=title,
            content=item.get("content", ""),
            source="tavily",
            url=url,
            semantic_score=None,
            metadata={},
        )
        by_id[cid] = cand

        if norm_title:
            title_to_ids.setdefault(norm_title, set()).add(cid)

    candidates = list(by_id.values())
    logger.info(f"[Pipeline] after dedup: {len(candidates)} candidates")
    return candidates


def assign_ranks(candidates: list[RetrievalCandidate]) -> None:
    """为 RAG 和 Tavily 结果分别生成 rank。

    RAG: 按 semantic_score 降序 → rag_rank = 1, 2, 3...
    Tavily: 按原始顺序 → tavily_rank = 1, 2, 3...
    """
    rag_items = sorted(
        [c for c in candidates if c.source == "rag" and c.semantic_score is not None],
        key=lambda c: c.semantic_score,
        reverse=True,
    )
    for i, c in enumerate(rag_items):
        c.rag_rank = i + 1

    tavily_items = [c for c in candidates if c.source == "tavily"]
    for i, c in enumerate(tavily_items):
        c.tavily_rank = i + 1


def rrf_fusion(candidates: list[RetrievalCandidate], rrf_k: int = RRF_K) -> None:
    """RRF Fusion：基于 rank 融合，不依赖原始 score。

    RRF_score(d) = Σ 1 / (RRF_K + rank)
    """
    for c in candidates:
        score = 0.0
        if c.rag_rank is not None:
            score += 1.0 / (rrf_k + c.rag_rank)
        if c.tavily_rank is not None:
            score += 1.0 / (rrf_k + c.tavily_rank)
        c.rrf_score = round(score, 6)

    logger.info(f"[Pipeline] RRF fusion (k={rrf_k}):")
    for c in sorted(candidates, key=lambda x: x.rrf_score, reverse=True):
        ranks = f"rag={c.rag_rank}, tavily={c.tavily_rank}"
        logger.info(f"[Pipeline]   {c.title}: rrf={c.rrf_score} ({ranks})")


def _min_max_normalize(values: list[float]) -> list[float]:
    """Min-Max 归一化到 [0, 1]。"""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return [1.0] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def ingredient_rerank(
    candidates: list[RetrievalCandidate],
    user_ingredients: list[dict],
) -> None:
    """计算 ingredient_match_score 和 final_score。"""
    user_names = [
        i.get("name", "")
        for i in user_ingredients
        if isinstance(i, dict) and i.get("name")
    ]

    # 归一化 RRF scores
    rrf_values = [c.rrf_score for c in candidates]
    normalized_rrf = _min_max_normalize(rrf_values)

    rrf_weight, ing_weight = _get_final_weights()
    logger.info(
        f"[Pipeline] final weights: rrf={rrf_weight}, ingredient={ing_weight}"
    )

    for i, c in enumerate(candidates):
        if user_names:
            recipe_ingredients = _extract_recipe_ingredients(c.content)
            user_norm = {_normalize_ingredient(n) for n in user_names if n.strip()}
            recipe_norm = {_normalize_ingredient(n) for n in recipe_ingredients if n.strip()}

            if user_norm:
                matched = user_norm & recipe_norm
                c.ingredient_match_score = round(len(matched) / len(user_norm), 4)
            else:
                c.ingredient_match_score = 0.0

            logger.info(
                f"[Pipeline]   ingredient: {c.title} "
                f"match={c.ingredient_match_score} "
                f"(recipe={recipe_ingredients[:5]}...)"
            )
        else:
            c.ingredient_match_score = 0.0

        c.final_score = round(
            normalized_rrf[i] * rrf_weight + c.ingredient_match_score * ing_weight,
            4,
        )

    logger.info("[Pipeline] final ranking:")
    for c in sorted(candidates, key=lambda x: x.final_score, reverse=True):
        logger.info(
            f"[Pipeline]   {c.title}: "
            f"rrf={c.rrf_score} (norm={normalized_rrf[candidates.index(c)]:.4f}), "
            f"ingredient={c.ingredient_match_score}, "
            f"final={c.final_score}"
        )


def run_retrieval_pipeline(
    rag_results: list[dict],
    tavily_results: list[dict],
    user_ingredients: list[dict],
    top_k: int = DEFAULT_FINAL_TOP_K,
) -> list[dict]:
    """完整检索 pipeline：Dedup → RRF → Ingredient Rerank → Top-K。

    Args:
        rag_results: RAG 检索结果（已经通过 threshold）
        tavily_results: Tavily 搜索结果
        user_ingredients: 用户当前食材 [{"name": "西红柿"}, ...]
        top_k: 最终返回数量

    Returns:
        list of dict: 与 RecipeAgent 兼容的格式
    """
    import time as _time
    from app.observability.trace import record_retrieval
    from app.observability.metrics import get_metrics_collector

    _pipeline_t0 = _time.time()

    if not rag_results and not tavily_results:
        logger.info("[Pipeline] 两路均无结果")
        return []

    _before_count = len(rag_results) + len(tavily_results)

    # Step 1: Dedup
    candidates = deduplicate(rag_results, tavily_results)
    _after_dedup = len(candidates)
    logger.info(f"[Pipeline] {len(candidates)} candidates after dedup")

    # ===== Observability: Dedup =====
    record_retrieval(
        "dedup",
        before=_before_count,
        after=_after_dedup,
        removed=_before_count - _after_dedup,
    )

    # Step 2: Assign ranks
    assign_ranks(candidates)

    # Step 3: RRF Fusion
    rrf_fusion(candidates)

    # ===== Observability: RRF =====
    for c in sorted(candidates, key=lambda x: x.rrf_score, reverse=True)[:5]:
        record_retrieval(
            "rrf",
            candidate=c.title,
            rag_rank=c.rag_rank or "none",
            tavily_rank=c.tavily_rank or "none",
            rrf_score=c.rrf_score,
        )

    # Step 4: Ingredient-aware Rerank
    ingredient_rerank(candidates, user_ingredients)

    # ===== Observability: Rerank =====
    for c in sorted(candidates, key=lambda x: x.final_score, reverse=True)[:top_k]:
        record_retrieval(
            "rerank",
            title=c.title,
            ingredient_match=c.ingredient_match_score,
            rrf_score=c.rrf_score,
            final_score=c.final_score,
        )

    # Step 5: Sort by final_score DESC, take Top-K
    candidates.sort(key=lambda c: c.final_score, reverse=True)
    final = candidates[:top_k]

    _pipeline_latency = int((_time.time() - _pipeline_t0) * 1000)
    record_retrieval(
        "rerank",
        final_top_k=len(final),
        pipeline_latency_ms=_pipeline_latency,
    )
    get_metrics_collector().record_retrieval_latency(_pipeline_latency)

    logger.info(f"[Pipeline] final top-{top_k}:")
    for i, c in enumerate(final):
        logger.info(
            f"[Pipeline]   {i + 1}. {c.title} "
            f"(source={c.source}, final={c.final_score})"
        )

    return [c.to_dict() for c in final]
