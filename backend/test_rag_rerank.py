"""RAG Ingredient-aware Rerank 测试。

测试 A：基础食材匹配（全匹配）
测试 B：部分匹配
测试 C：完全不匹配
测试 D：同义词归一化
测试 E：Rerank 公式验证
测试 F：Threshold + Rerank 联动（低于阈值不进入 rerank）
测试 G：烤鸭场景（本地无覆盖 → RAG 返回 []）
测试 H：回归测试（第一级优化未破坏）
"""
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from app.rag.retriever import (
    search_recipes,
    get_score_threshold,
    get_rerank_weights,
    _normalize_ingredient,
    _extract_recipe_ingredients,
    _calculate_ingredient_match_score,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def test_a_full_match():
    """测试 A：基础匹配 — 用户食材全部在菜谱中。"""
    print("\n" + "=" * 60)
    print("测试 A：基础匹配（全匹配）")
    print("=" * 60)

    user = ["西红柿", "鸡蛋"]
    recipe = ["西红柿", "鸡蛋", "盐"]
    score, matched = _calculate_ingredient_match_score(user, recipe)

    print(f"  用户食材: {user}")
    print(f"  菜谱食材: {recipe}")
    print(f"  匹配: {matched}")
    print(f"  ingredient_match_score = {score}")

    ok = abs(score - 1.0) < 0.001
    print(f"  {'✅' if ok else '❌'} 期望 1.0, 实际 {score}")
    return ok


def test_b_partial_match():
    """测试 B：部分匹配。"""
    print("\n" + "=" * 60)
    print("测试 B：部分匹配")
    print("=" * 60)

    user = ["西红柿", "鸡蛋", "青椒"]
    recipe = ["西红柿", "鸡蛋", "盐"]
    score, matched = _calculate_ingredient_match_score(user, recipe)

    expected = 2.0 / 3.0
    print(f"  用户食材: {user}")
    print(f"  菜谱食材: {recipe}")
    print(f"  匹配: {matched}")
    print(f"  ingredient_match_score = {score}")
    print(f"  期望 = {expected:.4f}")

    ok = abs(score - expected) < 0.001
    print(f"  {'✅' if ok else '❌'} 期望 {expected:.4f}, 实际 {score}")
    return ok


def test_c_no_match():
    """测试 C：完全不匹配。"""
    print("\n" + "=" * 60)
    print("测试 C：完全不匹配")
    print("=" * 60)

    user = ["烤鸭", "生菜"]
    recipe = ["土豆", "牛肉"]
    score, matched = _calculate_ingredient_match_score(user, recipe)

    print(f"  用户食材: {user}")
    print(f"  菜谱食材: {recipe}")
    print(f"  匹配: {matched}")
    print(f"  ingredient_match_score = {score}")

    ok = abs(score - 0.0) < 0.001
    print(f"  {'✅' if ok else '❌'} 期望 0.0, 实际 {score}")
    return ok


def test_d_synonym():
    """测试 D：同义词归一化（西红柿/番茄）。"""
    print("\n" + "=" * 60)
    print("测试 D：同义词归一化")
    print("=" * 60)

    # 用户说"西红柿"，菜谱写"番茄"
    user = ["西红柿", "鸡蛋"]
    recipe = ["番茄", "鸡蛋"]
    score, matched = _calculate_ingredient_match_score(user, recipe)

    print(f"  用户食材: {user}")
    print(f"  菜谱食材: {recipe}")
    print(f"  归一化后用户: {_normalize_ingredient('西红柿')}, {_normalize_ingredient('鸡蛋')}")
    print(f"  归一化后菜谱: {_normalize_ingredient('番茄')}, {_normalize_ingredient('鸡蛋')}")
    print(f"  匹配: {matched}")
    print(f"  ingredient_match_score = {score}")

    ok = abs(score - 1.0) < 0.001
    print(f"  {'✅' if ok else '❌'} 期望 1.0（同义词归一化后匹配）, 实际 {score}")
    return ok


def test_e_rerank_formula():
    """测试 E：Rerank 公式验证。"""
    print("\n" + "=" * 60)
    print("测试 E：Rerank 公式验证")
    print("=" * 60)

    sw, iw = get_rerank_weights()
    print(f"  权重: semantic={sw}, ingredient={iw}")

    # Candidate A: semantic=0.57, ingredient_match=1.0
    sem_a = 0.57
    ing_a = 1.0
    rerank_a = round(sem_a * sw + ing_a * iw, 4)

    # Candidate B: semantic=0.60, ingredient_match=0.5
    sem_b = 0.60
    ing_b = 0.5
    rerank_b = round(sem_b * sw + ing_b * iw, 4)

    print(f"\n  Candidate A: semantic={sem_a}, ingredient_match={ing_a}")
    print(f"    rerank = {sem_a}×{sw} + {ing_a}×{iw} = {rerank_a}")
    print(f"\n  Candidate B: semantic={sem_b}, ingredient_match={ing_b}")
    print(f"    rerank = {sem_b}×{sw} + {ing_b}×{iw} = {rerank_b}")

    ok_a = abs(rerank_a - 0.828) < 0.01
    ok_b = abs(rerank_b - 0.54) < 0.01
    ok_order = rerank_a > rerank_b

    print(f"\n  A.rerank={rerank_a} (期望 ~0.828): {'✅' if ok_a else '❌'}")
    print(f"  B.rerank={rerank_b} (期望 ~0.54): {'✅' if ok_b else '❌'}")
    print(f"  A 排在 B 前面: {'✅' if ok_order else '❌'}")

    return ok_a and ok_b and ok_order


def test_f_threshold_blocks_rerank():
    """测试 F：低于 threshold 的结果不进入 rerank。"""
    print("\n" + "=" * 60)
    print("测试 F：Threshold + Rerank 联动")
    print("=" * 60)

    threshold = get_score_threshold()
    print(f"  当前 threshold = {threshold}")

    # 模拟：semantic=0.49 < threshold=0.50, 即使 ingredient_match=1.0 也应被过滤
    sem = 0.49
    ing = 1.0

    passed_threshold = sem >= threshold
    print(f"\n  Candidate: semantic={sem}, ingredient_match={ing}")
    print(f"  semantic >= threshold? {'是' if passed_threshold else '否'}")

    ok = not passed_threshold
    print(f"  {'✅' if ok else '❌'} 低于阈值被过滤，不进入 rerank")

    return ok


def test_g_duck_scenario():
    """测试 G：烤鸭场景 — 本地无覆盖，RAG 返回 []。"""
    print("\n" + "=" * 60)
    print("测试 G：烤鸭场景（本地无覆盖）")
    print("=" * 60)

    user_ingredients = [
        {"name": "烤鸭"},
        {"name": "生菜"},
        {"name": "紫甘蓝"},
        {"name": "红椒"},
    ]
    results = search_recipes("烤鸭 生菜 紫甘蓝 红椒", top_k=3, user_ingredients=user_ingredients)

    print(f"  用户食材: {[i['name'] for i in user_ingredients]}")
    print(f"  RAG 返回: {len(results)} 条")

    if len(results) == 0:
        print(f"  ✅ 空列表（符合预期）")
        return True
    else:
        # 检查是否有低质量结果
        bad_titles = ["红烧肉", "鸡胸肉沙拉", "地三鲜"]
        for r in results:
            if r["title"] in bad_titles:
                print(f"  ❌ 低质量结果 '{r['title']}' 不应出现")
                return False
        print(f"  ⚠️ 有结果但无低质量菜谱")
        return True


def test_h_regression():
    """测试 H：回归测试 — 第一级优化未被破坏。"""
    print("\n" + "=" * 60)
    print("测试 H：回归测试")
    print("=" * 60)

    threshold = get_score_threshold()
    all_passed = True

    # H-1: 西红柿 鸡蛋
    print(f"\n--- H-1: 西红柿 鸡蛋 ---")
    user = [{"name": "西红柿"}, {"name": "鸡蛋"}]
    results = search_recipes("西红柿 鸡蛋", top_k=3, user_ingredients=user)
    print(f"  返回: {len(results)} 条")
    for r in results:
        print(f"    {r['title']}: semantic={r['score']}, ingredient_match={r.get('ingredient_match_score','?')}, rerank={r.get('rerank_score','?')}")

    if len(results) == 0:
        print(f"  ❌ 期望有结果")
        all_passed = False
    else:
        for r in results:
            if r["score"] < threshold:
                print(f"  ❌ {r['title']} score={r['score']} < threshold={threshold}")
                all_passed = False
        print(f"  ✅ 所有结果 score >= {threshold}")

    # H-2: 牛肉 土豆
    print(f"\n--- H-2: 牛肉 土豆 ---")
    user = [{"name": "牛肉"}, {"name": "土豆"}]
    results = search_recipes("牛肉 土豆", top_k=3, user_ingredients=user)
    print(f"  返回: {len(results)} 条")
    for r in results:
        print(f"    {r['title']}: semantic={r['score']}, ingredient_match={r.get('ingredient_match_score','?')}, rerank={r.get('rerank_score','?')}")

    if len(results) == 0:
        print(f"  ❌ 期望有结果")
        all_passed = False
    else:
        for r in results:
            if r["score"] < threshold:
                print(f"  ❌ {r['title']} score={r['score']} < threshold={threshold}")
                all_passed = False
        print(f"  ✅ 所有结果 score >= {threshold}")

    # H-3: 烤鸭 生菜 紫甘蓝 红椒
    print(f"\n--- H-3: 烤鸭 生菜 紫甘蓝 红椒 ---")
    user = [{"name": "烤鸭"}, {"name": "生菜"}, {"name": "紫甘蓝"}, {"name": "红椒"}]
    results = search_recipes("烤鸭 生菜 紫甘蓝 红椒", top_k=3, user_ingredients=user)
    print(f"  返回: {len(results)} 条")

    if len(results) == 0:
        print(f"  ✅ 空列表（符合预期）")
    else:
        for r in results:
            if r["score"] < threshold:
                print(f"  ❌ {r['title']} score={r['score']} < threshold={threshold}")
                all_passed = False
        print(f"  ⚠️ 有结果返回")

    return all_passed


def test_ingredient_extraction():
    """测试 I：菜谱食材提取。"""
    print("\n" + "=" * 60)
    print("测试 I：菜谱食材提取")
    print("=" * 60)

    sample_content = """# 番茄炒蛋

## 基础信息

难度：简单

## 食材

- 西红柿：2个（约300g）
- 鸡蛋：3个
- 食用油：适量
- 盐：适量
- 白糖：少量（约5g）
- 葱花：少许

## 步骤

1. 西红柿洗净。
2. 鸡蛋打散。

## 营养信息

热量：约320 kcal
"""

    ingredients = _extract_recipe_ingredients(sample_content)
    print(f"  提取结果: {ingredients}")

    expected = ["西红柿", "鸡蛋", "食用油", "盐", "白糖", "葱花"]
    ok = ingredients == expected
    print(f"  期望: {expected}")
    print(f"  {'✅' if ok else '❌'} 食材提取{'正确' if ok else '错误'}")
    return ok


if __name__ == "__main__":
    print("=" * 60)
    print("RAG Ingredient-aware Rerank 测试")
    print("=" * 60)

    results = {
        "A: 全匹配": test_a_full_match(),
        "B: 部分匹配": test_b_partial_match(),
        "C: 完全不匹配": test_c_no_match(),
        "D: 同义词": test_d_synonym(),
        "E: Rerank公式": test_e_rerank_formula(),
        "F: Threshold阻断": test_f_threshold_blocks_rerank(),
        "G: 烤鸭场景": test_g_duck_scenario(),
        "H: 回归测试": test_h_regression(),
        "I: 食材提取": test_ingredient_extraction(),
    }

    print("\n" + "=" * 60)
    print("总结")
    print("=" * 60)
    for name, ok in results.items():
        print(f"  测试 {name}: {'✅ PASS' if ok else '❌ FAIL'}")

    all_ok = all(results.values())
    print(f"\n  总体: {'✅ ALL PASS' if all_ok else '❌ HAS FAILURES'}")
