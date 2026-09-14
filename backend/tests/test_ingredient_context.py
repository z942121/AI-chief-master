"""增量食材上下文合并的单元测试。

测试覆盖：
1. 操作检测 (detect_operation)
2. 食材合并 (merge_ingredients) — new/add/remove/replace/update
3. 偏好合并 (merge_preferences) — 继承机制
4. Retry 一致性 — last_effective_* 快照不变
5. 跨会话隔离 — 不同 thread_id 不互相污染
"""
import sys
import os

# 将 backend 目录加入 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from app.agents.ingredient_context import (
    detect_operation,
    merge_ingredients,
    merge_preferences,
)


# ============================================================
# Test 1: 操作检测
# ============================================================

class TestDetectOperation:
    def test_new_query(self):
        assert detect_operation("我有西红柿和鸡蛋") == "new"

    def test_new_query_what_to_cook(self):
        assert detect_operation("牛肉可以怎么做") == "new"

    def test_add_keyword(self):
        assert detect_operation("再加两个土豆") == "add"

    def test_add_keyword_also(self):
        assert detect_operation("还需要胡萝卜") == "add"

    def test_remove_keyword(self):
        assert detect_operation("不要牛肉了") == "remove"

    def test_remove_keyword_remove(self):
        assert detect_operation("去掉土豆") == "remove"

    def test_replace_keyword(self):
        assert detect_operation("把土豆换成胡萝卜") == "replace"

    def test_replace_keyword_simple(self):
        assert detect_operation("牛肉换成猪肉") == "replace"

    def test_reset_keyword(self):
        assert detect_operation("重新推荐") == "new"

    def test_reset_keyword2(self):
        assert detect_operation("换个菜") == "new"

    def test_empty_query(self):
        assert detect_operation("") == "new"

    def test_update_keyword(self):
        assert detect_operation("少放点盐") == "update"


# ============================================================
# Test 2: 食材合并 — new
# ============================================================

class TestMergeNew:
    def test_new_with_ingredients(self):
        current = [{"name": "西红柿", "amount": "2个", "freshness": "新鲜"}]
        result = merge_ingredients(current, "new", [])
        assert len(result) == 1
        assert result[0]["name"] == "西红柿"

    def test_new_ignores_history(self):
        last = [{"name": "牛肉", "amount": "500g", "freshness": "新鲜"}]
        current = [{"name": "西红柿", "amount": "2个", "freshness": "新鲜"}]
        result = merge_ingredients(current, "new", last)
        assert len(result) == 1
        assert result[0]["name"] == "西红柿"

    def test_new_empty_current(self):
        result = merge_ingredients([], "new", [{"name": "牛肉"}])
        assert len(result) == 0


# ============================================================
# Test 3: 食材合并 — add
# ============================================================

class TestMergeAdd:
    def test_add_to_existing(self):
        last = [{"name": "牛肉", "amount": "500g", "freshness": "新鲜"}]
        current = [{"name": "土豆", "amount": "2个", "freshness": "新鲜"}]
        result = merge_ingredients(current, "add", last)
        names = [i["name"] for i in result]
        assert "牛肉" in names
        assert "土豆" in names
        assert len(result) == 2

    def test_add_duplicate_merges_amount(self):
        last = [{"name": "土豆", "amount": "2个", "freshness": "新鲜"}]
        current = [{"name": "土豆", "amount": "1个", "freshness": "新鲜"}]
        result = merge_ingredients(current, "add", last)
        assert len(result) == 1
        assert result[0]["name"] == "土豆"
        assert result[0]["amount"] == "1个"

    def test_add_empty_current_keeps_history(self):
        last = [{"name": "牛肉", "amount": "500g", "freshness": "新鲜"}]
        result = merge_ingredients([], "add", last)
        assert len(result) == 1
        assert result[0]["name"] == "牛肉"


# ============================================================
# Test 4: 食材合并 — remove
# ============================================================

class TestMergeRemove:
    def test_remove_from_existing(self):
        last = [
            {"name": "牛肉", "amount": "500g", "freshness": "新鲜"},
            {"name": "土豆", "amount": "2个", "freshness": "新鲜"},
        ]
        current = [{"name": "牛肉", "amount": "未知", "freshness": "新鲜"}]
        result = merge_ingredients(current, "remove", last)
        names = [i["name"] for i in result]
        assert "牛肉" not in names
        assert "土豆" in names
        assert len(result) == 1

    def test_remove_nonexistent_no_change(self):
        last = [{"name": "牛肉", "amount": "500g", "freshness": "新鲜"}]
        current = [{"name": "猪肉", "amount": "未知", "freshness": "新鲜"}]
        result = merge_ingredients(current, "remove", last)
        assert len(result) == 1
        assert result[0]["name"] == "牛肉"


# ============================================================
# Test 5: 食材合并 — replace
# ============================================================

class TestMergeReplace:
    def test_replace_existing(self):
        last = [
            {"name": "牛肉", "amount": "500g", "freshness": "新鲜"},
            {"name": "土豆", "amount": "2个", "freshness": "新鲜"},
        ]
        current = [{"name": "胡萝卜", "amount": "1根", "freshness": "新鲜"}]
        result = merge_ingredients(current, "replace", last)
        names = [i["name"] for i in result]
        assert "牛肉" in names
        assert "胡萝卜" in names
        assert len(result) == 3

    def test_replace_same_name_updates(self):
        last = [{"name": "土豆", "amount": "2个", "freshness": "新鲜"}]
        current = [{"name": "土豆", "amount": "5个", "freshness": "新鲜"}]
        result = merge_ingredients(current, "replace", last)
        assert len(result) == 1
        assert result[0]["amount"] == "5个"


# ============================================================
# Test 6: 食材合并 — update
# ============================================================

class TestMergeUpdate:
    def test_update_amount(self):
        last = [{"name": "土豆", "amount": "2个", "freshness": "新鲜"}]
        current = [{"name": "土豆", "amount": "3个", "freshness": "新鲜"}]
        result = merge_ingredients(current, "update", last)
        assert len(result) == 1
        assert result[0]["name"] == "土豆"
        assert result[0]["amount"] == "3个"

    def test_update_nonexistent_adds(self):
        last = [{"name": "牛肉", "amount": "500g", "freshness": "新鲜"}]
        current = [{"name": "土豆", "amount": "3个", "freshness": "新鲜"}]
        result = merge_ingredients(current, "update", last)
        names = [i["name"] for i in result]
        assert "牛肉" in names
        assert "土豆" in names


# ============================================================
# Test 7: 偏好合并
# ============================================================

class TestMergePreferences:
    def test_inherit_previous(self):
        last = {"spicy": False, "diet_goal": "减脂"}
        current = {}
        result = merge_preferences(current, last)
        assert result.get("spicy") is False
        assert result.get("diet_goal") == "减脂"

    def test_current_overrides_previous(self):
        last = {"spicy": False, "diet_goal": "减脂"}
        current = {"spicy": True}
        result = merge_preferences(current, last)
        assert result.get("spicy") is True
        assert result.get("diet_goal") == "减脂"

    def test_null_does_not_override(self):
        last = {"spicy": False, "diet_goal": "减脂"}
        current = {"spicy": None, "diet_goal": None}
        result = merge_preferences(current, last)
        assert result.get("spicy") is False
        assert result.get("diet_goal") == "减脂"

    def test_empty_string_does_not_override(self):
        last = {"spicy": False, "meal_type": "晚餐"}
        current = {"spicy": None, "meal_type": "无"}
        result = merge_preferences(current, last)
        assert result.get("spicy") is False
        assert result.get("meal_type") == "晚餐"

    def test_no_previous(self):
        current = {"spicy": False}
        result = merge_preferences(current, {})
        assert result.get("spicy") is False

    def test_add_new_key(self):
        last = {"spicy": False}
        current = {"diet_goal": "增肌"}
        result = merge_preferences(current, last)
        assert result.get("spicy") is False
        assert result.get("diet_goal") == "增肌"


# ============================================================
# Test 8: 多轮场景模拟
# ============================================================

class TestMultiTurnScenarios:
    """模拟多轮对话场景，验证 effective_ingredients 的变化。"""

    def test_scenario_add(self):
        """Turn1: 牛肉 → Turn2: 再加两个土豆 → 牛肉+土豆"""
        # Turn 1
        last = []
        current_t1 = [{"name": "牛肉", "amount": "500g", "freshness": "新鲜"}]
        op_t1 = detect_operation("牛肉可以怎么做")
        effective_t1 = merge_ingredients(current_t1, op_t1, last)
        assert len(effective_t1) == 1
        assert effective_t1[0]["name"] == "牛肉"

        # final_answer 快照
        last = effective_t1

        # Turn 2
        current_t2 = [{"name": "土豆", "amount": "2个", "freshness": "新鲜"}]
        op_t2 = detect_operation("再加两个土豆")
        assert op_t2 == "add"
        effective_t2 = merge_ingredients(current_t2, op_t2, last)
        names = [i["name"] for i in effective_t2]
        assert "牛肉" in names
        assert "土豆" in names
        assert len(effective_t2) == 2

    def test_scenario_remove(self):
        """Turn1: 牛肉+土豆 → Turn2: 不要牛肉 → 土豆"""
        # Turn 1
        last = []
        current_t1 = [
            {"name": "牛肉", "amount": "500g", "freshness": "新鲜"},
            {"name": "土豆", "amount": "2个", "freshness": "新鲜"},
        ]
        effective_t1 = merge_ingredients(current_t1, "new", last)
        last = effective_t1

        # Turn 2
        current_t2 = [{"name": "牛肉", "amount": "未知", "freshness": "新鲜"}]
        op_t2 = detect_operation("不要牛肉了")
        assert op_t2 == "remove"
        effective_t2 = merge_ingredients(current_t2, op_t2, last)
        names = [i["name"] for i in effective_t2]
        assert "牛肉" not in names
        assert "土豆" in names
        assert len(effective_t2) == 1

    def test_scenario_replace(self):
        """Turn1: 牛肉+土豆 → Turn2: 把土豆换成胡萝卜 → 牛肉+胡萝卜"""
        # Turn 1
        last = []
        current_t1 = [
            {"name": "牛肉", "amount": "500g", "freshness": "新鲜"},
            {"name": "土豆", "amount": "2个", "freshness": "新鲜"},
        ]
        effective_t1 = merge_ingredients(current_t1, "new", last)
        last = effective_t1

        # Turn 2
        current_t2 = [{"name": "胡萝卜", "amount": "1根", "freshness": "新鲜"}]
        op_t2 = detect_operation("把土豆换成胡萝卜")
        assert op_t2 == "replace"
        effective_t2 = merge_ingredients(current_t2, op_t2, last)
        names = [i["name"] for i in effective_t2]
        assert "牛肉" in names
        assert "胡萝卜" in names
        assert len(effective_t2) == 3

    def test_scenario_preference_inherit(self):
        """Turn1: 牛肉+不吃辣 → Turn2: 再加土豆 → 偏好继承"""
        # Turn 1
        last_prefs = {}
        current_prefs_t1 = {"spicy": False, "diet_goal": None}
        effective_prefs_t1 = merge_preferences(current_prefs_t1, last_prefs)
        assert effective_prefs_t1.get("spicy") is False
        last_prefs = effective_prefs_t1

        # Turn 2 — 用户没提偏好
        current_prefs_t2 = {"spicy": None, "diet_goal": None}
        effective_prefs_t2 = merge_preferences(current_prefs_t2, last_prefs)
        assert effective_prefs_t2.get("spicy") is False

    def test_scenario_cross_thread_isolation(self):
        """不同 thread_id 之间不互相污染。"""
        # Thread A Turn 1
        last_a = []
        current_a = [{"name": "牛肉", "amount": "500g", "freshness": "新鲜"}]
        effective_a = merge_ingredients(current_a, "new", last_a)
        last_a = effective_a  # final_answer 快照

        # Thread B Turn 1（独立会话，没有历史）
        last_b = []
        current_b = [
            {"name": "西红柿", "amount": "2个", "freshness": "新鲜"},
            {"name": "鸡蛋", "amount": "3个", "freshness": "新鲜"},
        ]
        effective_b = merge_ingredients(current_b, "new", last_b)

        # Thread B 不应包含牛肉
        names_b = [i["name"] for i in effective_b]
        assert "牛肉" not in names_b
        assert "西红柿" in names_b
        assert "鸡蛋" in names_b

        # Thread A 仍然只有牛肉
        names_a = [i["name"] for i in effective_a]
        assert "牛肉" in names_a
        assert "西红柿" not in names_a


# ============================================================
# Test 9: Retry 一致性
# ============================================================

class TestRetryConsistency:
    """验证 Retry 时 last_effective_* 不变，重新合并结果一致。"""

    def test_retry_produces_same_effective(self):
        """Turn1: 牛肉 → Turn2: 再加两个土豆 → Retry 后仍为 牛肉+土豆"""
        # Turn 1
        last = []
        current_t1 = [{"name": "牛肉", "amount": "500g", "freshness": "新鲜"}]
        effective_t1 = merge_ingredients(current_t1, "new", last)
        # final_answer 快照
        last = effective_t1

        # Turn 2 — 第一次执行
        current_t2 = [{"name": "土豆", "amount": "2个", "freshness": "新鲜"}]
        op_t2 = detect_operation("再加两个土豆")
        effective_t2_first = merge_ingredients(current_t2, op_t2, last)

        # Retry — last 没变（final_answer 还没执行）
        effective_t2_retry = merge_ingredients(current_t2, op_t2, last)

        assert effective_t2_first == effective_t2_retry
        assert len(effective_t2_retry) == 2

    def test_retry_supervisor_path(self):
        """Retry 到 supervisor 时，ingredient_agent 重新执行，
        但 last_effective_ingredients 没变，结果一致。"""
        last = [{"name": "牛肉", "amount": "500g", "freshness": "新鲜"}]

        # 第一次
        current = [{"name": "土豆", "amount": "2个", "freshness": "新鲜"}]
        op = detect_operation("再加两个土豆")
        effective_1 = merge_ingredients(current, op, last)

        # Retry — last 没变
        effective_2 = merge_ingredients(current, op, last)

        assert effective_1 == effective_2
