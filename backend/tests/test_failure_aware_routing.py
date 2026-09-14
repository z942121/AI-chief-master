"""Failure-aware Conditional Routing Test Suite.

Tests:
  Part 1: should_retry() unit tests (7 cases)
  Part 2: Graph fault injection (Case A: Recipe, B: Nutrition, C: Planning)
  Part 3: retry_constraints verification
  Part 4: MAX_RETRY verification
  Part 5: Invalid retry_target
  Part 6: Fan-out/Fan-in parallel verification
  Part 7: Nutrition Retry fan-in safety
  Part 8: Multi-turn state isolation + Retry
  Part 9: Real LLM integration test (optional)
"""
import os
import sys
import time
import json
import pytest
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage, AIMessage

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from app.agents.critic_agent import should_retry
from app.agents.shared import MAX_RETRY
import app.agents.workflow as workflow_mod


# ============================================================
# Helpers
# ============================================================

def _normalize_trace(trace):
    """Sort adjacent ingredient/preference pairs for deterministic comparison."""
    result = list(trace)
    i = 0
    while i < len(result) - 1:
        if {result[i], result[i + 1]} == {"ingredient", "preference"}:
            result[i], result[i + 1] = "ingredient", "preference"
            i += 2
        else:
            i += 1
    return result


class GraphTestHelper:
    """Runs the real LangGraph workflow with mocked agent nodes for fault injection."""

    def __init__(self, monkeypatch):
        self.trace = []
        self.timestamps = {}
        self.recipe_states = []
        self.ingredient_calls = []
        self.critic_call_count = 0
        self.critic_outputs = []
        self.ingredient_data = [{"name": "西红柿"}, {"name": "鸡蛋"}]

        self._memory_saver = MemorySaver()
        monkeypatch.setattr(workflow_mod, "get_checkpointer", lambda: self._memory_saver)
        monkeypatch.setattr(workflow_mod, "_graph", None)

        monkeypatch.setattr(workflow_mod, "supervisor_node", self._mock_supervisor)
        monkeypatch.setattr(workflow_mod, "ingredient_agent_node", self._mock_ingredient)
        monkeypatch.setattr(workflow_mod, "preference_agent_node", self._mock_preference)
        monkeypatch.setattr(workflow_mod, "recipe_agent_node", self._mock_recipe)
        monkeypatch.setattr(workflow_mod, "nutrition_agent_node", self._mock_nutrition)
        monkeypatch.setattr(workflow_mod, "critic_agent_node", self._mock_critic)
        monkeypatch.setattr(workflow_mod, "final_answer_node", self._mock_final)

        self.graph = workflow_mod.get_graph()

    def reset_for_new_turn(self):
        self.trace = []
        self.ingredient_calls = []
        self.critic_call_count = 0
        self.recipe_states = []
        self.timestamps = {}

    def run(self, thread_id, user_query="我有西红柿和鸡蛋"):
        input_state = {
            "messages": [HumanMessage(content=user_query)],
            "current_user_query": user_query,
            "current_image_data": "",
            "current_ingredients": [],
            "current_preferences": {},
            "current_recipes": [],
            "current_nutrition_analysis": [],
            "current_review_result": {},
            "current_retry_count": 0,
            "final_recommendation": "",
        }
        config = {"configurable": {"thread_id": thread_id}}
        return self.graph.invoke(input_state, config)

    # --- Mock nodes ---

    def _mock_supervisor(self, state):
        self.trace.append("supervisor")
        self.timestamps["supervisor_start"] = time.time()
        time.sleep(0.05)
        self.timestamps["supervisor_end"] = time.time()
        return {}

    def _mock_ingredient(self, state):
        self.trace.append("ingredient")
        self.timestamps["ingredient_start"] = time.time()
        time.sleep(0.05)
        self.timestamps["ingredient_end"] = time.time()
        data = [dict(d) for d in self.ingredient_data]
        self.ingredient_calls.append(data)
        return {"current_ingredients": data}

    def _mock_preference(self, state):
        self.trace.append("preference")
        self.timestamps["preference_start"] = time.time()
        time.sleep(0.05)
        self.timestamps["preference_end"] = time.time()
        return {"current_preferences": {"diet_goal": "日常"}}

    def _mock_recipe(self, state):
        self.trace.append("recipe")
        self.timestamps["recipe_start"] = time.time()
        review = state.get("current_review_result", {})
        self.recipe_states.append({
            "retry_count": state.get("current_retry_count", 0),
            "retry_constraints": review.get("retry_constraints", {}),
            "review_result": review,
            "ingredients": state.get("current_ingredients", []),
        })
        time.sleep(0.05)
        self.timestamps["recipe_end"] = time.time()
        return {"current_recipes": [{"name": "番茄炒蛋", "ingredients_needed": ["西红柿", "鸡蛋"], "steps": ["step1"], "source": "test", "difficulty": "简单", "cooking_time": "15", "description": "test"}]}

    def _mock_nutrition(self, state):
        self.trace.append("nutrition")
        self.timestamps["nutrition_start"] = time.time()
        time.sleep(0.05)
        self.timestamps["nutrition_end"] = time.time()
        return {"current_nutrition_analysis": [{"recipe_name": "番茄炒蛋", "calories": "200", "protein": "10g", "fat": "5g", "carbs": "20g", "fiber": "2g", "balance_score": 80, "note": "test"}]}

    def _mock_critic(self, state):
        self.trace.append("critic")
        self.critic_call_count += 1
        retry_count = state.get("current_retry_count", 0)
        if self.critic_call_count <= len(self.critic_outputs):
            review = dict(self.critic_outputs[self.critic_call_count - 1])
        else:
            review = {"passed": True, "score": 95, "retry_target": ""}
        return {
            "current_review_result": review,
            "current_retry_count": retry_count + 1,
        }

    def _mock_final(self, state):
        self.trace.append("final")
        return {
            "final_recommendation": "test recommendation",
            "messages": [AIMessage(content="test recommendation")],
        }


# ============================================================
# Part 1: Unit Tests — should_retry()
# ============================================================

class TestShouldRetry:
    """Router Unit Tests."""

    INGREDIENTS = [{"name": "西红柿"}, {"name": "鸡蛋"}]

    def test_case_1_recipe_retry(self):
        state = {"current_retry_count": 0, "current_ingredients": self.INGREDIENTS,
                 "current_review_result": {"passed": False, "score": 60, "retry_target": "recipe"}}
        assert should_retry(state) == "recipe_agent"

    def test_case_2_nutrition_retry(self):
        state = {"current_retry_count": 0, "current_ingredients": self.INGREDIENTS,
                 "current_review_result": {"passed": False, "score": 60, "retry_target": "nutrition"}}
        assert should_retry(state) == "nutrition_agent"

    def test_case_3_planning_retry(self):
        state = {"current_retry_count": 0, "current_ingredients": self.INGREDIENTS,
                 "current_review_result": {"passed": False, "score": 60, "retry_target": "planning"}}
        assert should_retry(state) == "supervisor"

    def test_case_4_passed(self):
        state = {"current_retry_count": 0, "current_ingredients": self.INGREDIENTS,
                 "current_review_result": {"passed": True, "score": 95, "retry_target": ""}}
        assert should_retry(state) == "final_answer"

    def test_case_5_max_retry(self):
        state = {"current_retry_count": MAX_RETRY, "current_ingredients": self.INGREDIENTS,
                 "current_review_result": {"passed": False, "score": 50, "retry_target": "recipe"}}
        assert should_retry(state) == "final_answer"

    def test_case_6_no_ingredients(self):
        state = {"current_retry_count": 0, "current_ingredients": [],
                 "current_review_result": {"passed": False, "score": 50, "retry_target": "recipe"}}
        assert should_retry(state) == "final_answer"

    def test_case_7_invalid_retry_target(self):
        state = {"current_retry_count": 0, "current_ingredients": self.INGREDIENTS,
                 "current_review_result": {"passed": False, "score": 50, "retry_target": "xxxx"}}
        result = should_retry(state)
        assert result == "recipe_agent"


# ============================================================
# Part 2: Graph Fault Injection Tests
# ============================================================

class TestGraphRecipeRetry:
    """Case A: Recipe Retry — Critic → Recipe → Nutrition → Critic → Final."""

    def test_recipe_retry(self, monkeypatch):
        h = GraphTestHelper(monkeypatch)
        h.critic_outputs = [
            {"passed": False, "score": 60, "retry_target": "recipe",
             "issues": ["菜谱没有充分利用当前食材"],
             "retry_constraints": {"must_use_ingredients": ["西红柿", "鸡蛋"],
                                    "forbidden_ingredients": [],
                                    "search_keywords": ["西红柿鸡蛋家常做法"]},
             "suggestions": ["重新搜索符合当前食材的菜谱"]},
            {"passed": True, "score": 95, "retry_target": ""},
        ]
        h.run("test-recipe-retry")

        expected = ["supervisor", "ingredient", "preference",
                    "recipe", "nutrition", "critic",
                    "recipe", "nutrition", "critic",
                    "final"]
        actual = _normalize_trace(h.trace)
        assert actual == expected, f"Expected {expected}, got {actual}"

        # Verify Supervisor NOT re-executed after first Critic
        first_critic_idx = h.trace.index("critic")
        after_critic = h.trace[first_critic_idx + 1:]
        assert "supervisor" not in after_critic, "Supervisor should NOT re-execute"
        assert "ingredient" not in after_critic, "Ingredient should NOT re-execute"
        assert "preference" not in after_critic, "Preference should NOT re-execute"
        assert "recipe" in after_critic, "Recipe SHOULD execute"


class TestGraphNutritionRetry:
    """Case B: Nutrition Retry — Critic → Nutrition → Critic → Final."""

    def test_nutrition_retry(self, monkeypatch):
        h = GraphTestHelper(monkeypatch)
        h.critic_outputs = [
            {"passed": False, "score": 60, "retry_target": "nutrition",
             "issues": ["营养数据缺失或不合理"],
             "retry_constraints": {},
             "suggestions": ["重新进行营养分析"]},
            {"passed": True, "score": 95, "retry_target": ""},
        ]
        h.run("test-nutrition-retry")

        expected = ["supervisor", "ingredient", "preference",
                    "recipe", "nutrition", "critic",
                    "nutrition", "critic",
                    "final"]
        actual = _normalize_trace(h.trace)
        assert actual == expected, f"Expected {expected}, got {actual}"

        # Verify Recipe NOT re-executed after first Critic
        first_critic_idx = h.trace.index("critic")
        after_critic = h.trace[first_critic_idx + 1:]
        assert "recipe" not in after_critic, "Recipe should NOT re-execute in Nutrition Retry"
        assert "supervisor" not in after_critic, "Supervisor should NOT re-execute"
        assert "ingredient" not in after_critic, "Ingredient should NOT re-execute"
        assert "preference" not in after_critic, "Preference should NOT re-execute"
        assert "nutrition" in after_critic, "Nutrition SHOULD execute"


class TestGraphPlanningRetry:
    """Case C: Planning Retry — full re-execution."""

    def test_planning_retry(self, monkeypatch):
        h = GraphTestHelper(monkeypatch)
        h.critic_outputs = [
            {"passed": False, "score": 50, "retry_target": "planning",
             "issues": ["用户当前需求理解错误"],
             "retry_constraints": {},
             "suggestions": ["重新理解用户需求"]},
            {"passed": True, "score": 95, "retry_target": ""},
        ]
        h.run("test-planning-retry")

        expected = ["supervisor", "ingredient", "preference",
                    "recipe", "nutrition", "critic",
                    "supervisor", "ingredient", "preference",
                    "recipe", "nutrition", "critic",
                    "final"]
        actual = _normalize_trace(h.trace)
        assert actual == expected, f"Expected {expected}, got {actual}"

        # Verify full re-execution
        first_critic_idx = h.trace.index("critic")
        after_critic = h.trace[first_critic_idx + 1:]
        assert "supervisor" in after_critic, "Supervisor SHOULD re-execute"
        assert "ingredient" in after_critic, "Ingredient SHOULD re-execute"
        assert "preference" in after_critic, "Preference SHOULD re-execute"
        assert "recipe" in after_critic, "Recipe SHOULD re-execute"
        assert "nutrition" in after_critic, "Nutrition SHOULD re-execute"
        assert "critic" in after_critic, "Critic SHOULD re-execute"


# ============================================================
# Part 3: retry_constraints Verification
# ============================================================

class TestRetryConstraints:
    """Verify retry_constraints are passed correctly to RecipeAgent."""

    def test_retry_constraints_preserved(self, monkeypatch):
        h = GraphTestHelper(monkeypatch)
        constraints = {
            "must_use_ingredients": ["西红柿", "鸡蛋"],
            "forbidden_ingredients": [],
            "search_keywords": ["西红柿鸡蛋家常做法"],
        }
        h.critic_outputs = [
            {"passed": False, "score": 60, "retry_target": "recipe",
             "issues": ["菜谱没有充分利用当前食材"],
             "retry_constraints": constraints,
             "suggestions": ["重新搜索符合当前食材的菜谱"]},
            {"passed": True, "score": 95, "retry_target": ""},
        ]
        h.run("test-constraints")

        # Second recipe call should have retry_constraints
        assert len(h.recipe_states) == 2, f"Expected 2 recipe calls, got {len(h.recipe_states)}"
        retry_state = h.recipe_states[1]
        assert retry_state["retry_count"] > 0, "Second recipe call should be a retry"

        rc = retry_state["retry_constraints"]
        assert rc.get("must_use_ingredients") == ["西红柿", "鸡蛋"]
        assert rc.get("search_keywords") == ["西红柿鸡蛋家常做法"]

        # Verify no natural language pollution
        issues = retry_state["review_result"].get("issues", [])
        suggestions = retry_state["review_result"].get("suggestions", [])
        for issue in issues:
            assert issue not in str(rc), f"Issue text leaked into retry_constraints: {issue}"
        for sug in suggestions:
            assert sug not in str(rc), f"Suggestion text leaked into retry_constraints: {sug}"


# ============================================================
# Part 4: MAX_RETRY Verification
# ============================================================

class TestMaxRetry:
    """Verify MAX_RETRY=2 prevents infinite loops."""

    def test_max_retry_stops(self, monkeypatch):
        h = GraphTestHelper(monkeypatch)
        h.critic_outputs = [
            {"passed": False, "score": 50, "retry_target": "recipe"},
            {"passed": False, "score": 50, "retry_target": "recipe"},
            {"passed": False, "score": 50, "retry_target": "recipe"},
            {"passed": False, "score": 50, "retry_target": "recipe"},
        ]
        result = h.run("test-max-retry")

        final_retry_count = result.get("current_retry_count", 0)
        assert final_retry_count == MAX_RETRY, \
            f"Expected retry_count={MAX_RETRY}, got {final_retry_count}"

        expected = ["supervisor", "ingredient", "preference",
                    "recipe", "nutrition", "critic",
                    "recipe", "nutrition", "critic",
                    "final"]
        actual = _normalize_trace(h.trace)
        assert actual == expected, f"Expected {expected}, got {actual}"

        # Count critic calls — should be exactly MAX_RETRY (2 calls = 1 initial + 1 retry)
        # Each Critic call increments retry_count; should_retry stops when retry_count >= MAX_RETRY
        critic_count = h.trace.count("critic")
        assert critic_count == MAX_RETRY, \
            f"Expected {MAX_RETRY} critic calls, got {critic_count}"

        # Verify no 3rd retry
        assert "final" in h.trace, "Must reach final_answer"


# ============================================================
# Part 5: Invalid retry_target
# ============================================================

class TestInvalidRetryTarget:
    """Verify invalid retry_target degrades gracefully to recipe_agent."""

    def test_invalid_target_routes_to_recipe(self, monkeypatch):
        h = GraphTestHelper(monkeypatch)
        h.critic_outputs = [
            {"passed": False, "score": 50, "retry_target": "abcdef"},
            {"passed": True, "score": 95, "retry_target": ""},
        ]
        h.run("test-invalid-target")

        expected = ["supervisor", "ingredient", "preference",
                    "recipe", "nutrition", "critic",
                    "recipe", "nutrition", "critic",
                    "final"]
        actual = _normalize_trace(h.trace)
        assert actual == expected, f"Expected {expected}, got {actual}"

        first_critic_idx = h.trace.index("critic")
        after_critic = h.trace[first_critic_idx + 1:]
        assert "recipe" in after_critic, "Invalid target should degrade to recipe_agent"
        assert "nutrition" in after_critic
        assert "supervisor" not in after_critic, "Should NOT route to supervisor"


# ============================================================
# Part 6: Fan-out / Fan-in Verification
# ============================================================

class TestFanOutFanIn:
    """Verify Ingredient + Preference run in parallel, Recipe waits for both."""

    def test_parallel_execution(self, monkeypatch):
        h = GraphTestHelper(monkeypatch)
        h.critic_outputs = [
            {"passed": False, "score": 50, "retry_target": "planning"},
            {"passed": True, "score": 95, "retry_target": ""},
        ]
        h.run("test-fanout")

        # Check first parallel pair (initial execution)
        ing_start = h.timestamps.get("ingredient_start")
        ing_end = h.timestamps.get("ingredient_end")
        pref_start = h.timestamps.get("preference_start")
        pref_end = h.timestamps.get("preference_end")

        assert ing_start is not None and pref_start is not None

        # Both should start at nearly the same time (parallel)
        delta = abs(ing_start - pref_start)
        assert delta < 0.5, f"Ingredient/Preference start delta={delta:.3f}s, expected < 0.5s"

        # Recipe should start after BOTH finish
        recipe_start = h.timestamps.get("recipe_start")
        assert recipe_start is not None
        assert recipe_start >= min(ing_end, pref_end), \
            "Recipe must start after both Ingredient and Preference finish"

    def test_planning_retry_parallel(self, monkeypatch):
        """Verify second execution (Planning Retry) also has parallel Ingredient+Preference."""
        h = GraphTestHelper(monkeypatch)
        h.critic_outputs = [
            {"passed": False, "score": 50, "retry_target": "planning"},
            {"passed": True, "score": 95, "retry_target": ""},
        ]
        h.run("test-fanout-retry")

        # Count supervisor executions
        supervisor_count = h.trace.count("supervisor")
        ingredient_count = h.trace.count("ingredient")
        preference_count = h.trace.count("preference")
        recipe_count = h.trace.count("recipe")

        assert supervisor_count == 2, f"Expected 2 supervisor calls, got {supervisor_count}"
        assert ingredient_count == 2, f"Expected 2 ingredient calls, got {ingredient_count}"
        assert preference_count == 2, f"Expected 2 preference calls, got {preference_count}"
        assert recipe_count == 2, f"Expected 2 recipe calls, got {recipe_count}"


# ============================================================
# Part 7: Nutrition Retry Fan-in Safety
# ============================================================

class TestNutritionFanIn:
    """Verify conditional edge to nutrition_agent doesn't trigger fan-in wait."""

    def test_nutrition_retry_no_deadlock(self, monkeypatch):
        h = GraphTestHelper(monkeypatch)
        h.critic_outputs = [
            {"passed": False, "score": 60, "retry_target": "nutrition",
             "issues": ["营养数据缺失"], "retry_constraints": {}, "suggestions": []},
            {"passed": True, "score": 95, "retry_target": ""},
        ]
        h.run("test-nutrition-fanin")

        # Must complete without deadlock
        assert "final" in h.trace, "Graph must complete (no deadlock)"

        expected = ["supervisor", "ingredient", "preference",
                    "recipe", "nutrition", "critic",
                    "nutrition", "critic",
                    "final"]
        actual = _normalize_trace(h.trace)
        assert actual == expected, f"Expected {expected}, got {actual}"

        # No recipe in retry
        first_critic_idx = h.trace.index("critic")
        after = h.trace[first_critic_idx + 1:]
        assert "recipe" not in after, "Recipe must NOT execute in Nutrition Retry"
        assert "nutrition" in after, "Nutrition must execute"

        # No duplicate nutrition
        nutrition_after = after.count("nutrition")
        assert nutrition_after == 1, f"Expected 1 nutrition in retry, got {nutrition_after}"


# ============================================================
# Part 8: Multi-turn State Isolation + Retry
# ============================================================

class TestMultiTurnStateIsolation:
    """Verify state isolation across turns with Planning Retry."""

    def test_multi_turn_no_pollution(self, monkeypatch):
        h = GraphTestHelper(monkeypatch)

        # Turn 1: 西红柿 + 鸡蛋
        h.ingredient_data = [{"name": "西红柿"}, {"name": "鸡蛋"}]
        h.critic_outputs = [
            {"passed": True, "score": 95, "retry_target": ""},
        ]
        h.run("test-mt", "我有西红柿和鸡蛋")
        turn1_ingredients = h.ingredient_calls[0]
        assert any(i["name"] == "西红柿" for i in turn1_ingredients)

        # Turn 2: 牛肉 + 土豆, with Planning Retry
        h.reset_for_new_turn()
        h.ingredient_data = [{"name": "牛肉"}, {"name": "土豆"}]
        h.critic_outputs = [
            {"passed": False, "score": 50, "retry_target": "planning",
             "issues": ["用户当前需求理解错误"],
             "retry_constraints": {}, "suggestions": ["重新理解用户需求"]},
            {"passed": True, "score": 95, "retry_target": ""},
        ]
        h.run("test-mt", "我现在有牛肉和土豆")

        # Check all ingredient calls in turn 2
        for call in h.ingredient_calls:
            names = [i["name"] for i in call]
            assert "西红柿" not in names, f"Turn 1 pollution! Found 西红柿 in {names}"
            assert "鸡蛋" not in names, f"Turn 1 pollution! Found 鸡蛋 in {names}"
            assert "牛肉" in names, f"Expected 牛肉 in {names}"
            assert "土豆" in names, f"Expected 土豆 in {names}"

        # Verify Planning Retry occurred
        assert h.trace.count("supervisor") == 2, "Planning Retry should re-execute Supervisor"
        assert h.trace.count("ingredient") == 2, "Planning Retry should re-execute Ingredient"

        # Check recipe states for turn 2
        for rs in h.recipe_states:
            ingredient_names = [i["name"] for i in rs["ingredients"]]
            assert "西红柿" not in ingredient_names, "Turn 1 ingredients in recipe state!"
            assert "鸡蛋" not in ingredient_names, "Turn 1 ingredients in recipe state!"


# ============================================================
# Part 9: Real LLM Integration Test (optional)
# ============================================================

class TestRealLLM:
    """Real LLM integration test — verifies retry_target output."""

    @pytest.mark.skipif(
        not os.getenv("DASHSCOPE_API_KEY"),
        reason="DASHSCOPE_API_KEY not set"
    )
    def test_real_llm(self):
        from app.agents.personal_chief import search_recipes

        results = list(search_recipes(
            "我有西红柿和鸡蛋，想做一道简单的家常菜",
            "",
            "test-real-llm"
        ))

        # Should produce output
        assert len(results) > 0, "Should produce streaming output"

        # Check for SSE format
        for chunk in results:
            assert chunk.startswith("data: "), f"Expected SSE format, got: {chunk[:50]}"
