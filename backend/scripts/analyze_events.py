import json, sys
from collections import Counter
from pathlib import Path

def main(path: str) -> None:
    file = Path(path)
    if not file.exists() or file.stat().st_size == 0:
        print("没有可分析的事件数据。"); return
    events = [json.loads(line) for line in file.read_text(encoding="utf-8").splitlines() if line.strip()]
    sessions = {e.get("session_id") for e in events}; starts = {e.get("session_id") for e in events if e.get("event_name") == "search_session_start"}
    payloads = [e.get("payload", {}) for e in events]; suggestions = [p.get("suggestion_count") for p in payloads if isinstance(p.get("suggestion_count"), (int,float))]
    clicks = [p for e,p in zip(events,payloads) if e.get("event_name") == "platform_link_clicked"]
    selected = sum(p.get("count", 1) for e,p in zip(events,payloads) if e.get("event_name") == "keyword_selection_changed")
    removed = sum(p.get("count", 1) for e,p in zip(events,payloads) if e.get("event_name") == "keyword_removed_by_user")
    added = sum(p.get("count", 1) for e,p in zip(events,payloads) if e.get("event_name") == "keyword_added_by_user")
    feedback = [p.get("helpful") for e,p in zip(events,payloads) if e.get("event_name") == "search_feedback_submitted"]
    times = [p["elapsed_ms"] for e,p in zip(events,payloads) if e.get("event_name") == "platform_link_clicked" and isinstance(p.get("elapsed_ms"),(int,float))]
    pct = lambda n, d: f"{n / d:.2%}" if d else "0.00%"
    print(f"搜索会话数: {len(sessions)}\n文本 / 图片搜索会话数: {sum(p.get('entry')=='text' for p in payloads)} / {sum(p.get('entry')=='image' for p in payloads)}\n平均 suggestion 数: {sum(suggestions)/len(suggestions) if suggestions else 0:.2f}\n关键词选择次数: {selected}\n关键词删除率: {pct(removed, selected+removed)}")
    print(f"用户新增词比例: {pct(added, added+selected+removed)}\n搜索发起率: {pct(len(starts), len(sessions))}\n平台点击次数及平台点击占比: {len(clicks)} / {dict(Counter(p.get('platform') for p in clicks))}\n用户反馈满意率: {pct(sum(feedback), len(feedback))}\n平均首次平台点击耗时: {sum(times)/len(times) if times else 0:.0f} ms\ndegraded 会话占比: {pct(sum(bool(p.get('degraded')) for p in payloads), len(sessions))}\nprovider 分布: {dict(Counter(p.get('provider') for p in payloads if p.get('provider')))}")
if __name__ == "__main__": main(sys.argv[1] if len(sys.argv) > 1 else "backend/logs/events.jsonl")
