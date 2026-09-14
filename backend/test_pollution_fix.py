import sys, os, json, logging, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

from app.agents.personal_chief import search_recipes, get_messages, clear_messages

def run_test(thread_id, prompt, image=''):
    full = ''
    for chunk in search_recipes(prompt, image, thread_id):
        if chunk.startswith('data: '):
            data = chunk[6:].strip()
            try:
                text = json.loads(data)
                full += text
            except:
                pass
    return full

def extract_main_dish(text):
    """从 Markdown 中提取主要推荐的菜名（## 后的第一个标题）"""
    m = re.search(r'##\s+[^\n]*([\u4e00-\u9fa5]{2,15}(?:炒|焖|烤|煮|蒸|煎|烧|炖|饭|汤|面|肉|鸡|鸭|牛|猪|蛋|茄|豆)[\u4e00-\u9fa5]{0,15})', text)
    if m:
        return m.group(1)
    return None

# ========== TEST A ==========
print('=' * 60)
print('TEST A: 验证第二轮食材不被第一轮污染')
print('=' * 60)

thread_a = 'test_pollution_fix_A2'
clear_messages(thread_a)

print('\n--- Turn 1: 我有西红柿和鸡蛋 ---')
full1 = run_test(thread_a, '我有西红柿和鸡蛋')
dish1 = extract_main_dish(full1)
t1_tomato = '西红柿' in full1
t1_egg = '鸡蛋' in full1
t1_duck = '烤鸭' in full1
print(f'  主菜: {dish1}')
print(f'  含西红柿: {t1_tomato}')
print(f'  含鸡蛋: {t1_egg}')
print(f'  含烤鸭: {t1_duck}')
print(f'  长度: {len(full1)}')

print('\n--- Turn 2: 我有一只烤鸭，可以做什么菜 ---')
full2 = run_test(thread_a, '我有一只烤鸭，可以做什么菜')
dish2 = extract_main_dish(full2)
t2_duck = '烤鸭' in full2
# 污染判断：是否推荐了西红柿炒鸡蛋（上一轮的菜）
t2_tomato_egg_dish = '西红柿炒鸡蛋' in full2 or '番茄炒蛋' in full2
# 正常提到"鸡蛋"不算污染（炒饭等菜谱本身含鸡蛋）
t2_tomato_pollution = '西红柿' in full2 and dish2 and '西红柿' in dish2
print(f'  主菜: {dish2}')
print(f'  含烤鸭: {t2_duck}')
print(f'  推荐了西红柿炒鸡蛋（污染）: {t2_tomato_egg_dish}')
print(f'  主菜含西红柿（污染）: {t2_tomato_pollution}')
print(f'  长度: {len(full2)}')
print(f'  前300字:\n{full2[:300]}')

print('\n--- 历史消息检查 ---')
msgs = get_messages(thread_a)
print(f'  历史消息数: {len(msgs)}')
for m in msgs:
    role = m.get('role', '?')
    content = m.get('content', '')
    short = content[:60] + '...' if len(content) > 60 else content
    print(f'    [{role}] {short}')

# 污染判定：主菜围绕烤鸭 + 没有推荐西红柿炒鸡蛋
pollution_a = t2_tomato_egg_dish or t2_tomato_pollution
result_a = '✅ PASS' if (t2_duck and not pollution_a and dish2 and '烤鸭' in dish2) else '❌ FAIL'
print(f'\nTEST A 结果: {result_a}')
print(f'  主菜为烤鸭相关: {"是 ✅" if dish2 and "烤鸭" in dish2 else "否 ❌"} ({dish2})')
print(f'  西红柿炒鸡蛋污染: {"是 ❌" if t2_tomato_egg_dish else "否 ✅"}')

# ========== TEST B ==========
print('\n' + '=' * 60)
print('TEST B: 第三轮不同食材验证')
print('=' * 60)

print('\n--- Turn 3: 我有土豆和牛肉 ---')
full3 = run_test(thread_a, '我有土豆和牛肉，推荐一个快手菜')
dish3 = extract_main_dish(full3)
t3_beef = '牛肉' in full3 or '土豆' in full3
t3_duck_in_dish = dish3 and '烤鸭' in dish3
t3_tomato_in_dish = dish3 and '西红柿' in dish3
print(f'  主菜: {dish3}')
print(f'  含牛肉/土豆: {t3_beef}')
print(f'  主菜含烤鸭: {bool(t3_duck_in_dish)}')
print(f'  主菜含西红柿: {bool(t3_tomato_in_dish)}')
print(f'  长度: {len(full3)}')
print(f'  前200字:\n{full3[:200]}')

pollution_b = bool(t3_duck_in_dish or t3_tomato_in_dish)
result_b = '✅ PASS' if (t3_beef and not pollution_b and dish3) else '❌ FAIL'
print(f'\nTEST B 结果: {result_b}')
print(f'  牛肉土豆相关: {"是 ✅" if dish3 else "否 ❌"} ({dish3})')
print(f'  烤鸭/西红柿污染: {"是 ❌" if pollution_b else "否 ✅"}')

# ========== TEST C ==========
print('\n' + '=' * 60)
print('TEST C: 语义上下文（追问理解）')
print('=' * 60)

thread_c = 'test_context_C2'
clear_messages(thread_c)

print('\n--- Turn 1: 推荐西红柿炒蛋 ---')
full_c1 = run_test(thread_c, '我有西红柿和鸡蛋，推荐一个简单的菜')
dish_c1 = extract_main_dish(full_c1)
print(f'  主菜: {dish_c1}')
print(f'  长度: {len(full_c1)}')

print('\n--- Turn 2: 这个怎么做详细点? ---')
full_c2 = run_test(thread_c, '这个怎么做详细点')
dish_c2 = extract_main_dish(full_c2)
c2_has_detail = len(full_c2) > 300
c2_not_error = '暂无法生成' not in full_c2 and '无法为您' not in full_c2
print(f'  主菜/主题: {dish_c2}')
print(f'  回复长度: {len(full_c2)}')
print(f'  不是错误回复: {c2_not_error}')
print(f'  前200字:\n{full_c2[:200]}')

result_c = '✅ PASS' if (c2_has_detail and c2_not_error) else '❌ FAIL'
print(f'\nTEST C 结果: {result_c}')
print(f'  追问得到有意义回答: {"是 ✅" if c2_not_error else "否 ❌"}')

# ========== 总览 ==========
print('\n' + '=' * 60)
print('测试总览')
print('=' * 60)
print(f'  TEST A (食材隔离-烤鸭替换西红柿鸡蛋): {result_a}')
print(f'  TEST B (三轮隔离-牛肉土豆): {result_b}')
print(f'  TEST C (语义理解-追问): {result_c}')
print('=' * 60)
