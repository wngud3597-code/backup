import requests


class WikipediaClient:
    HEADERS = {
        "User-Agent": "StackOverflowingBot/1.0 (SSAFY AI Core Project; contact@ssafy.io)"
    }

    BASE_URL_EN = "https://en.wikipedia.org/api/rest_v1/page/summary"
    BASE_URL_KO = "https://ko.wikipedia.org/api/rest_v1/page/summary"
    SEARCH_URL_EN = "https://en.wikipedia.org/w/api.php"

    # 알파벳 한 글자 언어들의 위키백과 공식 표제어 매핑
    SPECIAL_TITLE_MAP = {
        "c": "C (programming language)",
        "r": "R (programming language)",
        "go": "Go (programming language)",
        "d": "D (programming language)",
    }

    @classmethod
    def search_candidates(cls, query: str, limit: int = 3) -> list[dict]:
        clean_q = query.strip().lower()
        if clean_q in cls.SPECIAL_TITLE_MAP:
            target = cls.SPECIAL_TITLE_MAP[clean_q]
            return [
                {
                    "candidate_id": f"wiki_{target.replace(' ', '_')}",
                    "title": target,
                    "url": f"https://en.wikipedia.org/wiki/{target.replace(' ', '_')}",
                    "source_kind": "wikipedia",
                }
            ]

        params = {
            "action": "opensearch",
            "search": query,
            "limit": limit,
            "namespace": 0,
            "format": "json",
        }
        try:
            resp = requests.get(
                cls.SEARCH_URL_EN, headers=cls.HEADERS, params=params, timeout=5
            )
            if resp.status_code == 200:
                data = resp.json()
                titles = data[1] if len(data) > 1 else []
                urls = data[3] if len(data) > 3 else []

                candidates = []
                for i, title in enumerate(titles):
                    candidates.append(
                        {
                            "candidate_id": f"wiki_{title.replace(' ', '_')}",
                            "title": title,
                            "url": urls[i]
                            if i < len(urls)
                            else f"https://en.wikipedia.org/wiki/{title}",
                            "source_kind": "wikipedia",
                        }
                    )
                return candidates
        except Exception:
            pass
        return []

    @classmethod
    def fetch_page_summary(cls, title: str) -> dict | None:
        clean_t = title.strip().lower()
        target_title = cls.SPECIAL_TITLE_MAP.get(clean_t, title)
        safe_title = requests.utils.quote(target_title.replace(" ", "_"))

        # 1. 영문 위키 조회
        url_en = f"{cls.BASE_URL_EN}/{safe_title}"
        try:
            resp = requests.get(url_en, headers=cls.HEADERS, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("extract"):
                    return {
                        "title": data.get("title", target_title),
                        "text": data.get("extract", ""),
                        "url": data.get("content_urls", {})
                        .get("desktop", {})
                        .get("page", url_en),
                        "description": data.get("description", ""),
                    }
        except Exception:
            pass

        # 2. 한글 위키 조회 (Fallback)
        url_ko = f"{cls.BASE_URL_KO}/{safe_title}"
        try:
            resp = requests.get(url_ko, headers=cls.HEADERS, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("extract"):
                    return {
                        "title": data.get("title", target_title),
                        "text": data.get("extract", ""),
                        "url": data.get("content_urls", {})
                        .get("desktop", {})
                        .get("page", url_ko),
                        "description": data.get("description", ""),
                    }
        except Exception:
            pass

        return None
