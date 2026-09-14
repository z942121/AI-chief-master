"""RAG Similarity Threshold Filtering 测试。

测试 A：阈值比较逻辑单元测试
  1. score=0.60, threshold=0.50 → 保留
  2. score=0.50, threshold=0.50 → 保留（>= 比较）
  3. score=0.49, threshold=0.50 → 过滤
  4. 全部低于阈值 → []

测试 B：实际检索验证
  1. "西红柿 鸡蛋" → 保留高相关结果
  2. "牛肉 土豆" → 保留土豆炖牛肉等
  3. "烤鸭 生菜 紫甘蓝 红椒" → 返回 []（本地无覆盖）
"""
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from app.rag.retriever import search_recipes, get_score_threshold

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def test_threshold_logic():
    """测试 A：阈值比较逻辑。"""
    print("\n" + "=" * 60)
    print("测试 A：阈值比较逻辑")
    print("=" * 60)

    threshold = 0.50
    passed = 0
    failed = 0

    cases = [
        ("score=0.60 >= threshold=0.50", 0.60, True),
        ("score=0.50 >= threshold=0.50", 0.50, True),
        ("score=0.49 >= threshold=0.50", 0.49, False),
    ]

    for name, score, expect_keep in cases:
        kept = score >= threshold
        ok = kept == expect_keep
        status = "✅" if ok else "❌"
        print(f"  {status} {name}: {'保留' if kept else '过滤'} (期望: {'保留' if expect_keep else '过滤'})")
        if ok:
            passed += 1
        else:
            failed += 1

    # 测试 4：全部低于阈值 → []
    print(f"  测试 4：全部低于阈值 → 结果应为空")
    scores = [0.41, 0.40, 0.39]
    accepted = [s for s in scores if s >= threshold]
    ok = len(accepted) == 0
    status = "✅" if ok else "❌"
    print(f"  {status} 输入 {scores} → accepted={accepted} (期望: [])")
    if ok:
        passed += 1
    else:
        failed += 1

    print(f"\n  结果: {passed} passed, {failed} failed")
    return failed == 0


def test_real_retrieval():
    """测试 B：实际检索验证。"""
    print("\n" + "=" * 60)
    print("测试 B：实际检索验证")
    print("=" * 60)

    threshold = get_score_threshold()
    print(f"当前 RAG_SCORE_THRESHOLD = {threshold}\n")

    test_cases = [
        {
            "query": "西红柿 鸡蛋",
            "name": "西红柿鸡蛋（本地有覆盖）",
            "expect_nonempty": True,
            "should_not_contain": None,
        },
        {
            "query": "牛肉 土豆",
            "name": "牛肉土豆（本地有覆盖）",
            "expect_nonempty": True,
            "should_not_contain": None,
        },
        {
            "query": "烤鸭 生菜 紫甘蓝 红椒",
            "name": "烤鸭生菜紫甘蓝红椒（本地无覆盖）",
            "expect_nonempty": False,
            "should_not_contain": ["红烧肉", "鸡胸肉沙拉", "地三鲜"],
        },
    ]

    all_passed = True

    for tc in test_cases:
        print(f"\n--- 查询: {tc['query']} ---")
        print(f"    预期: {'有结果' if tc['expect_nonempty'] else '空列表'}")

        results = search_recipes(tc["query"], top_k=3)
        print(f"    实际返回: {len(results)} 条")

        for r in results:
            print(f"      - {r['title']}: {r['score']}")

        if tc["expect_nonempty"]:
            if len(results) > 0:
                print(f"    ✅ 有结果（符合预期）")
            else:
                print(f"    ❌ 期望有结果但返回空")
                all_passed = False
        else:
            if len(results) == 0:
                print(f"    ✅ 空列表（符合预期）")
            else:
                print(f"    ❌ 期望空列表但有结果返回")
                all_passed = False

        # 检查不应出现的结果
        if tc["should_not_contain"]:
            titles = [r["title"] for r in results]
            for bad in tc["should_not_contain"]:
                if bad in titles:
                    print(f"    ❌ 低相关结果 '{bad}' 不应出现")
                    all_passed = False

        # 检查所有返回结果的 score >= threshold
        for r in results:
            if r["score"] < threshold:
                print(f"    ❌ {r['title']} score={r['score']} < threshold={threshold}")
                all_passed = False

    return all_passed


def test_content_completeness():
    """测试 C：返回结果包含完整菜谱内容。"""
    print("\n" + "=" * 60)
    print("测试 C：返回结果包含完整菜谱内容")
    print("=" * 60)

    results = search_recipes("西红柿 鸡蛋", top_k=3)
    all_complete = True

    for r in results:
        content = r["content"]
        has_ingredients = "食材" in content
        has_steps = "步骤" in content
        is_complete = has_ingredients and has_steps
        status = "✅" if is_complete else "❌"
        print(f"  {status} {r['title']}: 食材={has_ingredients}, 步骤={has_steps}")
        if not is_complete:
            all_complete = False

    return all_complete


if __name__ == "__main__":
    print("=" * 60)
    print("RAG Similarity Threshold Filtering 测试")
    print("=" * 60)

    a_ok = test_threshold_logic()
    b_ok = test_real_retrieval()
    c_ok = test_content_completeness()

    print("\n" + "=" * 60)
    print("总结")
    print("=" * 60)
    print(f"  测试 A（阈值逻辑）:    {'✅ PASS' if a_ok else '❌ FAIL'}")
    print(f"  测试 B（实际检索）:    {'✅ PASS' if b_ok else '❌ FAIL'}")
    print(f"  测试 C（内容完整性）:  {'✅ PASS' if c_ok else '❌ FAIL'}")
    print(f"  总体: {'✅ ALL PASS' if (a_ok and b_ok and c_ok) else '❌ HAS FAILURES'}")
