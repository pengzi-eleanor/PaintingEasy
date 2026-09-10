from datetime import datetime, timezone
from typing import Any
from app.config import Settings, get_settings
from app.analytics_provider import AnalyticsProvider, JsonlAnalyticsProvider, NoopAnalyticsProvider

EVENT_NAMES = {"search_session_start", "keyword_suggestions_generated", "keyword_selection_changed", "keyword_added_by_user", "keyword_removed_by_user", "platform_links_generated", "platform_link_clicked", "keyword_regenerated", "image_uploaded", "image_analysis_completed", "search_feedback_submitted"}
def query_language(value: str) -> str:
    if not value: return "unknown"
    zh, en = any("\u4e00" <= c <= "\u9fff" for c in value), any(c.isascii() and c.isalpha() for c in value)
    return "mixed" if zh and en else "zh" if zh else "en" if en else "unknown"

class AnalyticsService:
    def __init__(self, provider: AnalyticsProvider | None = None, settings: Settings | None = None):
        settings = settings or get_settings(); self.enabled = settings.analytics_enabled; self.record_raw_query = settings.analytics_record_raw_query
        self.provider = provider or (JsonlAnalyticsProvider(settings.analytics_log_path) if settings.analytics_provider == "jsonl" else NoopAnalyticsProvider())
    def track(self, event_name: str, session_id: str, payload: dict[str, Any] | None = None) -> bool:
        if event_name not in EVENT_NAMES or not session_id: raise ValueError("invalid event_name or session_id")
        data = dict(payload or {})
        if "query" in data:
            query = str(data.pop("query")); data["query_length"] = len(query); data["query_language"] = query_language(query)
            if self.record_raw_query: data["query"] = query
        try:
            if self.enabled: self.provider.write({"event_name": event_name, "session_id": session_id, "timestamp": datetime.now(timezone.utc).isoformat(), "payload": data})
        except Exception: return False
        return True
