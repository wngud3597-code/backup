import json
from typing import Any

from config import STORAGE_DIR

CACHE_FILE = STORAGE_DIR / "wiki_collection_cache.json"


class CollectionCache:
    def __init__(self):
        self.cache_file = CACHE_FILE
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if self.cache_file.exists():
            try:
                return json.loads(self.cache_file.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save(self):
        self.cache_file.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def get_document(self, key: str) -> dict[str, Any] | None:
        return self._data.get(key)

    def set_document(self, key: str, doc_data: dict[str, Any]):
        self._data[key] = doc_data
        self._save()


# 싱글톤 캐시
wiki_cache = CollectionCache()
