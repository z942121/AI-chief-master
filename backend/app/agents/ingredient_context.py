"""增量食材上下文合并模块。

负责：
1. 从用户查询中识别食材操作类型（new/add/remove/replace/update）
2. 根据操作类型将当前轮食材与上一轮有效食材合并
3. 合并偏好（当前轮偏好覆盖上一轮，未提及的继承）

设计要点：
- last_effective_ingredients / last_effective_preferences 由 final_answer 更新，
  在整个当前轮内不变，因此 Retry 时重新合并结果一致
- 不同 thread_id 之间完全隔离（Checkpointer 按 thread_id 隔离）
"""
import re
import logging

logger = logging.getLogger(__name__)

# ===== 操作类型关键词 =====
# 顺序很重要：先匹配更具体的关键词
_REMOVE_KEYWORDS = [
    "不要", "去掉", "不用", "拿掉", "去掉", "不放", "去掉",
    "没有", "没了", "吃完", "用完",
]
_REPLACE_KEYWORDS = [
    "换成", "替换", "把.*换", "换掉",
]
_ADD_KEYWORDS = [
    "再加", "另外加", "还需要", "除此之外", "再放",
    "多加", "加点", "加一些", "加上", "再来", "还有",
    "再加一个", "再加两个", "再加三个",
]
_RESET_KEYWORDS = [
    "换个菜", "重新来", "重新推荐", "重新做",
    "我现在有", "这次只用", "这次有", "换一个",
    "不吃了", "换个口味", "全新",
]
_UPDATE_KEYWORDS = [
    "少放", "减半", "加倍", "减量", "增量",
    "多放点", "少用点",
]


def detect_operation(user_query: str) -> str:
    """从用户查询中检测食材操作类型。

    Returns:
        "new" | "add" | "remove" | "replace" | "update"
    """
    if not user_query:
        return "new"

    query = user_query.strip()

    # 1. 检查 replace（替换）
    for kw in _REPLACE_KEYWORDS:
        if re.search(kw, query):
            return "replace"

    # 2. 检查 remove（删除）
    for kw in _REMOVE_KEYWORDS:
        if kw in query:
            return "remove"

    # 3. 检查 reset（明确重新开始）
    for kw in _RESET_KEYWORDS:
        if kw in query:
            return "new"

    # 4. 检查 update（修改数量）
    for kw in _UPDATE_KEYWORDS:
        if kw in query:
            # "再加一个土豆" → 如果已有土豆，是 update；否则是 add
            # 这里返回 update，merge 时会处理
            return "update"

    # 5. 检查 add（增量添加）
    for kw in _ADD_KEYWORDS:
        if kw in query:
            return "add"

    # 6. 默认：新查询
    return "new"


def _normalize_name(name: str) -> str:
    """标准化食材名称用于比较。"""
    return name.strip().lower().replace(" ", "")


def _merge_amounts(existing_amount: str, new_amount: str) -> str:
    """合并两个食材的份量描述。"""
    if not existing_amount or existing_amount == "未知":
        return new_amount or "未知"
    if not new_amount or new_amount == "未知":
        return existing_amount
    # 如果两者都有效，优先使用新的（用户明确说了新数量）
    return new_amount


def merge_ingredients(
    current_ingredients: list[dict],
    operation: str,
    last_effective: list[dict],
) -> list[dict]:
    """根据操作类型合并食材。

    Args:
        current_ingredients: 当前轮提取的食材
        operation: 操作类型 new/add/remove/replace/update
        last_effective: 上一轮的有效食材

    Returns:
        合并后的有效食材列表
    """
    if operation == "new" or not last_effective:
        return list(current_ingredients) if current_ingredients else []

    if operation == "add":
        result = [dict(item) for item in last_effective]
        for new_item in current_ingredients:
            new_name = _normalize_name(new_item.get("name", ""))
            found = False
            for existing in result:
                if _normalize_name(existing.get("name", "")) == new_name:
                    existing["amount"] = _merge_amounts(
                        existing.get("amount", ""), new_item.get("amount", "")
                    )
                    found = True
                    break
            if not found:
                result.append(dict(new_item))
        return result

    if operation == "remove":
        result = []
        remove_names = {
            _normalize_name(i.get("name", ""))
            for i in current_ingredients
            if i.get("name")
        }
        for existing in last_effective:
            if _normalize_name(existing.get("name", "")) not in remove_names:
                result.append(dict(existing))
        return result

    if operation == "replace":
        # current_ingredients 中的是新食材，last_effective 中同名的被替换
        # 但实际上 replace 的"旧食材"也需要从 current_ingredients 中提取
        # 这里简化：current_ingredients 包含新食材，旧食材通过 remove_ingredients 处理
        # 由于 LLM 可能不区分，我们用名称匹配：如果 current 中有与 last 中同名的，替换；否则添加
        result = [dict(item) for item in last_effective]
        for new_item in current_ingredients:
            new_name = _normalize_name(new_item.get("name", ""))
            found = False
            for i, existing in enumerate(result):
                if _normalize_name(existing.get("name", "")) == new_name:
                    result[i] = dict(new_item)
                    found = True
                    break
            if not found:
                result.append(dict(new_item))
        return result

    if operation == "update":
        result = [dict(item) for item in last_effective]
        for new_item in current_ingredients:
            new_name = _normalize_name(new_item.get("name", ""))
            for existing in result:
                if _normalize_name(existing.get("name", "")) == new_name:
                    existing["amount"] = new_item.get("amount", existing.get("amount", "未知"))
                    break
            else:
                # 食材不存在于历史中，当作新增
                result.append(dict(new_item))
        return result

    # fallback
    return list(current_ingredients) if current_ingredients else []


def merge_preferences(
    current_preferences: dict,
    last_effective: dict,
) -> dict:
    """合并偏好：当前轮非 null 值覆盖上一轮，null 值继承上一轮。

    Args:
        current_preferences: 当前轮提取的偏好
        last_effective: 上一轮的有效偏好

    Returns:
        合并后的有效偏好
    """
    if not last_effective:
        return dict(current_preferences) if current_preferences else {}

    if not current_preferences:
        return dict(last_effective)

    result = dict(last_effective)
    for key, value in current_preferences.items():
        if value is not None and value != "" and value != "无":
            result[key] = value
    return result
