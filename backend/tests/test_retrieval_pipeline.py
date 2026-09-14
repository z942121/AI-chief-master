"""检索层 Pipeline 测试：Dedup + RRF + Ingredient Rerank。

Test A: RRF 基本公式
Test B: 双路都有的 candidate RRF
Test C: Dedup URL
Test D: Dedup 标题相同内容不同 → 保留两个
Test E: Ingredient Match + Final Score
Test F: 同义词归一化
Test G: 完整 pipeline 端到端
Test H: RAG-only (Tavily 空)
Test I: Tavily-only (RAG 空)
Test J: Top-K 截断
Test K: 归一化防除零
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from app.rag.retrieval_pipeline import (
    RetrievalCandidate,
    deduplicate,
    assign_ranks,
    rrf_fusion,
    ingredient_rerank,
    run_retrieval_pipeline,
    _normalize_title,
    _make_id,
    _min_max_normalize,
    RRF_K,
)


# ============================================================
# Test A: RRF 基本公式
# ============================================================

class TestRRFBasic:
    def test_rag_only_rrf(self):
        c = RetrievalCandidate(id="1", title="A", content="", source="rag", rag_rank=1)
        rrf_fusion([c])
        expected = 1.0 / (RRF_K + 1)
        assert abs(c.rrf_score - round(expected, 6)) < 1e-6

    def test_tavily_only_rrf(self):
        c = RetrievalCandidate(id="2", title="B", content="", source="tavily", tavily_rank=3)
        rrf_fusion([c])
        expected = 1.0 / (RRF_K + 3)
        assert abs(c.rrf_score - round(expected, 6)) < 1e-6

    def test_dual_source_rrf(self):
        c = RetrievalCandidate(
            id="3", title="C", content="", source="rag",
            rag_rank=1, tavily_rank=4,
        )
        rrf_fusion([c])
        expected = 1.0 / (RRF_K + 1) + 1.0 / (RRF_K + 4)
        assert abs(c.rrf_score - round(expected, 6)) < 1e-6


# ============================================================
# Test B: 双路都有 candidate RRF > 单路
# ============================================================

class TestDualSourceBoost:
    def test_dual_higher_than_single(self):
        c1 = RetrievalCandidate(id="a", title="A", content="", source="rag", rag_rank=1)
        c2 = RetrievalCandidate(
            id="b", title="B", content="", source="rag",
            rag_rank=2, tavily_rank=1,
        )
        rrf_fusion([c1, c2])
        assert c2.rrf_score > c1.rrf_score, "Dual-source should have higher RRF"


# ============================================================
# Test C: Dedup URL
# ============================================================

class TestDedupURL:
    def test_same_url_dedup(self):
        rag = [{"title": "番茄炒蛋", "content": "rag content", "url": "http://example.com/1"}]
        tavily = [{"title": "番茄炒蛋(网页版)", "content": "tavily content", "url": "http://example.com/1"}]
        result = deduplicate(rag, tavily)
        assert len(result) == 1, f"Expected 1 after URL dedup, got {len(result)}"


# ============================================================
# Test D: 标题相同内容不同 → 保留两个
# ============================================================

class TestSameTitleDifferentContent:
    def test_keep_both(self):
        rag = [{"title": "番茄炒蛋", "content": "RAG 版本完整菜谱内容...", "url": ""}]
        tavily = [{"title": "番茄炒蛋", "content": "Tavily 版本不同的菜谱内容...", "url": ""}]
        result = deduplicate(rag, tavily)
        assert len(result) == 2, f"Expected 2 (different content), got {len(result)}"


# ============================================================
# Test E: Ingredient Match + Final Score
# ============================================================

class TestIngredientMatch:
    def test_full_match(self):
        candidates = [
            RetrievalCandidate(
                id="1", title="番茄炒蛋", source="rag",
                content="## 食材\n- 番茄：2个\n- 鸡蛋：3个\n- 盐：适量\n## 步骤\n...",
                rag_rank=1,
            ),
        ]
        rrf_fusion(candidates)
        ingredient_rerank(candidates, [{"name": "西红柿"}, {"name": "鸡蛋"}])
        assert candidates[0].ingredient_match_score == 1.0
        assert candidates[0].final_score > 0

    def test_partial_match(self):
        candidates = [
            RetrievalCandidate(
                id="1", title="番茄炒蛋", source="rag",
                content="## 食材\n- 番茄：2个\n- 鸡蛋：3个\n",
                rag_rank=1,
            ),
        ]
        rrf_fusion(candidates)
        ingredient_rerank(candidates, [{"name": "西红柿"}, {"name": "鸡蛋"}, {"name": "青椒"}])
        assert abs(candidates[0].ingredient_match_score - 2.0 / 3.0) < 0.01

    def test_no_match(self):
        candidates = [
            RetrievalCandidate(
                id="1", title="红烧肉", source="rag",
                content="## 食材\n- 五花肉：500g\n- 酱油：适量\n",
                rag_rank=1,
            ),
        ]
        rrf_fusion(candidates)
        ingredient_rerank(candidates, [{"name": "西红柿"}, {"name": "鸡蛋"}])
        assert candidates[0].ingredient_match_score == 0.0


# ============================================================
# Test F: 同义词归一化
# ============================================================

class TestSynonymNormalization:
    def test_synonym_match(self):
        candidates = [
            RetrievalCandidate(
                id="1", title="番茄炒蛋", source="rag",
                content="## 食材\n- 番茄：2个\n- 鸡蛋：3个\n",
                rag_rank=1,
            ),
        ]
        rrf_fusion(candidates)
        ingredient_rerank(candidates, [{"name": "西红柿"}, {"name": "鸡蛋"}])
        assert candidates[0].ingredient_match_score == 1.0, "西红柿 should match 番茄"


# ============================================================
# Test G: 完整 pipeline 端到端
# ============================================================

class TestEndToEnd:
    def test_full_pipeline(self):
        rag = [
            {"title": "番茄炒蛋", "content": "## 食材\n- 番茄：2个\n- 鸡蛋：3个\n## 步骤\n...", "url": "", "score": 0.58},
            {"title": "西红柿鸡蛋汤", "content": "## 食材\n- 西红柿：2个\n- 鸡蛋：2个\n## 步骤\n...", "url": "", "score": 0.55},
        ]
        tavily = [
            {"title": "番茄牛肉汤", "content": "需要番茄和牛肉...", "url": "http://example.com/beef"},
            {"title": "番茄炒蛋做法", "content": "番茄炒蛋的家常做法...", "url": "http://example.com/egg"},
        ]
        user_ingredients = [{"name": "西红柿"}, {"name": "鸡蛋"}]

        result = run_retrieval_pipeline(rag, tavily, user_ingredients, top_k=3)

        assert len(result) <= 3
        assert len(result) > 0

        # 番茄炒蛋 should rank high (matches both ingredients)
        titles = [r["title"] for r in result]
        assert "番茄炒蛋" in titles or "西红柿鸡蛋汤" in titles

        # Check fields
        for r in result:
            assert "title" in r
            assert "content" in r
            assert "source" in r
            assert "score" in r
            assert "ingredient_match_score" in r
            assert "rrf_score" in r
            assert "rerank_score" in r

    def test_rag_higher_when_matching(self):
        """RAG candidate with full ingredient match should rank higher than Tavily with no match."""
        rag = [
            {"title": "番茄炒蛋", "content": "## 食材\n- 番茄：2个\n- 鸡蛋：3个\n", "url": "", "score": 0.55},
        ]
        tavily = [
            {"title": "红烧肉", "content": "需要五花肉和酱油...", "url": "http://example.com/pork"},
        ]
        user_ingredients = [{"name": "西红柿"}, {"name": "鸡蛋"}]

        result = run_retrieval_pipeline(rag, tavily, user_ingredients, top_k=2)
        assert result[0]["title"] == "番茄炒蛋", "RAG with full match should rank first"


# ============================================================
# Test H: RAG-only (Tavily 空)
# ============================================================

class TestRagOnly:
    def test_rag_only_works(self):
        rag = [
            {"title": "番茄炒蛋", "content": "## 食材\n- 番茄：2个\n- 鸡蛋：3个\n", "url": "", "score": 0.58},
        ]
        result = run_retrieval_pipeline(rag, [], [{"name": "西红柿"}, {"name": "鸡蛋"}], top_k=3)
        assert len(result) == 1
        assert result[0]["source"] == "rag"


# ============================================================
# Test I: Tavily-only (RAG 空)
# ============================================================

class TestTavilyOnly:
    def test_tavily_only_works(self):
        tavily = [
            {"title": "番茄炒蛋", "content": "家常做法...", "url": "http://example.com/1"},
        ]
        result = run_retrieval_pipeline([], tavily, [{"name": "西红柿"}], top_k=3)
        assert len(result) == 1
        assert result[0]["source"] == "tavily"


# ============================================================
# Test J: Top-K 截断
# ============================================================

class TestTopK:
    def test_top_k_truncation(self):
        rag = [
            {"title": f"菜谱{i}", "content": f"## 食材\n- 番茄\n", "url": "", "score": 0.5 - i * 0.01}
            for i in range(5)
        ]
        tavily = [
            {"title": f"网页菜谱{i}", "content": "...", "url": f"http://example.com/{i}"}
            for i in range(5)
        ]
        result = run_retrieval_pipeline(rag, tavily, [{"name": "西红柿"}], top_k=3)
        assert len(result) == 3, f"Expected 3, got {len(result)}"


# ============================================================
# Test K: 归一化防除零
# ============================================================

class TestNormalize:
    def test_all_same_values(self):
        result = _min_max_normalize([0.5, 0.5, 0.5])
        assert all(abs(v - 1.0) < 1e-6 for v in result), "All same → all 1.0"

    def test_empty(self):
        assert _min_max_normalize([]) == []

    def test_normal(self):
        result = _min_max_normalize([1.0, 2.0, 3.0])
        assert abs(result[0] - 0.0) < 1e-6
        assert abs(result[1] - 0.5) < 1e-6
        assert abs(result[2] - 1.0) < 1e-6


# ============================================================
# Test L: 完整 pipeline 空输入
# ============================================================

class TestEmptyInput:
    def test_both_empty(self):
        result = run_retrieval_pipeline([], [], [{"name": "西红柿"}], top_k=3)
        assert result == []

    def test_no_user_ingredients(self):
        rag = [{"title": "番茄炒蛋", "content": "## 食材\n- 番茄\n", "url": "", "score": 0.58}]
        result = run_retrieval_pipeline(rag, [], [], top_k=3)
        assert len(result) == 1
        assert result[0]["ingredient_match_score"] == 0.0
