"""SSE 端到端验证：3 条真实查询，验证 0.35 threshold 下完整链路。"""
import json
import sys

import httpx

BASE = "http://localhost:8001/api/v1/chat/stream"

QUERIES = [
    "我有西红柿和鸡蛋",
    "我有牛肉和土豆",
    "我有西红柿和鸡蛋，不吃辣",
]

for i, q in enumerate(QUERIES, 1):
    thread_id = f"verify-threshold035-{i:03d}"
    print(f"===== QUERY {i}: {q} (thread={thread_id}) =====", flush=True)

    events = {"status": 0, "chunk": 0, "done": 0, "error": 0}
    answer_parts = []
    error_msg = None
    cur_event = None

    try:
        with httpx.Client(timeout=300.0) as client:
            with client.stream(
                "POST", BASE, json={"message": q, "thread_id": thread_id}
            ) as resp:
                print(f"HTTP {resp.status_code} {resp.headers.get('content-type', '')}", flush=True)
                for line in resp.iter_lines():
                    if line.startswith("event:"):
                        cur_event = line.split(":", 1)[1].strip()
                    elif line.startswith("data:") and cur_event:
                        payload = line.split(":", 1)[1].strip()
                        try:
                            data = json.loads(payload)
                        except (json.JSONDecodeError, ValueError):
                            data = {}
                        if cur_event in events:
                            events[cur_event] += 1
                        if cur_event == "chunk":
                            answer_parts.append(data.get("content", ""))
                        elif cur_event == "error":
                            error_msg = data.get("message", payload)
                        elif cur_event == "status":
                            print(f"  [status] {data.get('stage')}:{data.get('status')} {data.get('message', '')}", flush=True)
    except Exception as e:
        print(f"EXCEPTION: {type(e).__name__}: {e}", flush=True)

    print(f"events: {events}", flush=True)
    if error_msg:
        print(f"ERROR event: {error_msg}", flush=True)
    answer = "".join(answer_parts)
    print(f"answer length: {len(answer)} chars", flush=True)
    print(f"answer head: {answer[:200]}", flush=True)
    print(f"answer tail: {answer[-150:]}", flush=True)
    print("", flush=True)

print("ALL SSE QUERIES DONE", flush=True)
