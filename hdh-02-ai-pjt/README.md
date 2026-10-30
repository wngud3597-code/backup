
# 🚀 StackOverflowing (개발자 기술 동향 RAG 네비게이터)

> **Stack Overflow Developer Survey 2026** 기반의 하이브리드 RAG (정형 통계 SQLite + Chroma 벡터 검색 + LangGraph 2-노드) 아키텍처를 적용한 기술 의사결정 지원 플랫폼입니다.

---

## 📌 1. 프로젝트 개요

* **도메인:** Stack Overflow Developer Survey 2026 (프로그래밍 언어, 데이터베이스, 웹 프레임워크, 클라우드 등 104대 기술 생태계)
* **핵심 아키텍처:**
  1. **정형 통계 분리 (결정적 수치 보장):** 사용률(Usage), 관심도(Desired), 만족도(Admired), n수 등 수치 데이터는 **SQLite 파라미터화 쿼리**로 계산하여 LLM의 환각(Hallucination)을 원천 차단.
  2. **지식 문맥 보강 (Chroma 2개 컬렉션 + 실시간 위키백과):** 설문 방법론/지표 정의 및 기술별 아키텍처 문서는 벡터 DB와 Wikipedia REST API로 수집하여 객관적 근거(Evidence)로 제공.
  3. **LangGraph 2-노드 파이프라인:** 명세에 따른 엄격한 `retrieve` ➔ `generate` 단방향 상태 전이 및 문장 단위 인용 일치 검증기 적용.

---

## 🛠️ 2. 빠른 실행 방법 (Getting Started)

본 프로젝트는 고속 패키지 관리자 `uv`를 기본으로 사용합니다.

### 1) 환경 준비 및 패키지 설치
```bash
# 필수 의존성 패키지 설치
uv add "langchain==1.3.14" "langgraph==1.2.10" "langsmith==0.10.17" "langchain-core==1.6.0" "langchain-openai==1.4.3" "langchain-community==0.4.2" "langchain-chroma==1.1.0" "langchain-text-splitters==1.1.2" "chromadb==1.5.9" "openai==2.54.0" "streamlit==1.62.0" "requests==2.34.2" "python-dotenv==1.2.3" "typing-extensions==4.16.0"
```

### 2) 환경변수 설정 (`.env`)
`.env.example`을 복사하여 `.env`를 생성하고 본인의 API 키를 입력합니다.
```bash
OPENAI_API_KEY=your_gms_or_openai_api_key_here
OPENAI_BASE_URL=https://gms.ssafy.io/gmsapi/api.openai.com/v1   # SSAFY GMS 사용 시
OPENAI_CHAT_MODEL=gpt-4o-mini                                  # 또는 sol / gpt-4o
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

### 3) 데이터베이스 초기화 및 인덱싱 (최초 1회 실행)
```bash
# 1. 104개 기술 메타데이터 및 설문 관측치 SQLite 적재 (F2001)
uv run python -m data.items

# 2. 기술 메타데이터 컬렉션(so_tech_meta_v1) 색인 (F2002)
uv run python -m indexing.metadata

# 3. 설문 공식 정의/방법론 컬렉션(so_survey_docs_v1) 색인 (F2005)
uv run python -m indexing.documents
```

### 4) Streamlit 웹 애플리케이션 실행
```bash
uv run streamlit run app.py
```

---

## ✨ 3. 전체 기능 설명 (요구사항 매핑)

### [필수 기능 (F2001 ~ F2012)]
* **F2001 (100건 이상 항목 로드):** 언어(32), DB(26), 클라우드(20), 웹 프레임워크(26) 총 104개 고유 기술 데이터 적재.
* **F2002 (항목 메타데이터 색인):** `so_tech_meta_v1` 컬렉션에 기술당 1건씩 104건 멱등 색인 보장.
* **F2003 / F2004 (외부 검색어 추출 및 후보 선별/수집):** 프롬프트 A/B 및 위키백과 공식 REST API 연동, 선택 기술 자체 문서 강제 우선 포함.
* **F2005 (조정 청킹 및 별도 컬렉션):** 설문 정의/방법론 및 외부 위키 문서를 `so_survey_docs_v1` 컬렉션으로 분리 격리.
* **F2006 (두 컬렉션 병합 및 강제 포함):** 선택된 기술 메타데이터를 유사도 순위와 무관하게 근거 1번에 고정 포함.
* **F2007 (LangGraph 2-노드 아키텍처):** `retrieve` ➔ `generate` 단방향 상태 전이 파이프라인 준수. 근거 부족 시 `insufficient` 보류.
* **F2008 (인용 출처 100% 일치 표기):** 본문의 `[근거 n]`과 하단 아코디언 출처 리스트의 완전 일치 검증기(`rag/citations.py`).
* **F2009 (항목별 대화 세션 분리):** 사이드바에서 기술 변경 시 이전 기술과의 대화 내역 오염 0건 격리.
* **F2010 (도메인 특화 기능):** 단일 연도 3대 지표(`Usage` vs `Desired` vs `Admired`) 교차 갭 분석 및 생태계 지속성 진단.
* **F2011 (자연어 조건 탐색):** LLM이 질의에서 조건(수치, 카테고리, 용도)을 JSON으로 추출하여 SQLite 정밀 필터링.
* **F2012 (진행 상태 및 표본 한계 고지):** 실시간 스피너 상태 안내 및 설문 표본의 비확률적 한계 상시 면책 고지.

### [비기능적 요구사항 (NF2001 ~ NF2007)]
* **NF2002 (영속 캐시):** `storage/wiki_collection_cache.json`을 통해 동일 검색어/문서의 외부 API 재호출 원천 차단.
* **NF2003 / NF2004 (보안 및 정보 비노출):** API 키 환경변수 분리, UI 및 로그 상 Traceback 및 프롬프트 전문 비노출 처리.
* **NF2006 (외부 API 예절):** 위키미디어 필수 정책을 준수하는 `User-Agent` 식별 헤더 탑재 (403 차단 방지).
* **NF2007 (출처 및 라이선스 준수):** Stack Overflow ODbL 1.0 라이선스 표기 및 원문 표 locator 추적.

### [추천·의사결정 확장 기능]
* **🌐 전체 생태계 자유 질의:** 특정 기술을 고르지 않아도 사용자의 아키텍처 요구사항(예: "AI 백엔드 추천")을 읽어 다중 기술을 자동 비교.
* **🛠️ 맞춤형 풀스택 추천기:** 프로젝트 목적과 우선가치에 맞춰 [언어-웹-DB-클라우드] 4개 레이어를 AI가 직접 설계.
* **🔄 지능형 대안 탐색:** 특정 기술(예: MySQL) 대비 동종 분야의 실질적 대안(PostgreSQL, MariaDB 등)과 트레이드오프 비교.
* **🩺 내 기술 스택 건강성 진단:** 사용 중인 기술들을 종합 진찰하여 아키텍처적 시너지와 주의사항 리포트 제공.

---

## 📊 4. 데이터 파이프라인 및 아키텍처

```text
[공식 설문 원천 데이터] ──> [data/items.py] ──> [SQLite: observation / technology]
                                  │
                                  ├──> [indexing/metadata.py] ──> [Chroma: so_tech_meta_v1]
                                  │
[설문 정의 / 방법론 문맥] ───────────┴──> [indexing/documents.py] ─> [Chroma: so_survey_docs_v1]
                                  ▲
[실시간 위키백과 REST API] ─────────┘ (collection/service.py 동적 색인)
```

1. **정형 통계:** 기술 104개에 대한 2026 설문 관측치(Usage, Desired, Admired, n수)를 SQLite에 정규화 저장.
2. **기술 메타데이터:** 검색 편의를 위해 기술명, 범주, 요약 설명 텍스트를 `so_tech_meta_v1`에 1:1 벡터 색인.
3. **설문 정의 및 방법론:** 지표 정의(Admired 분모 규약 등)와 표본 한계 문서를 `so_survey_docs_v1`에 청킹 색인.
4. **외부 기술 문서:** 질의 시 실시간으로 위키백과 공식 문서를 수집하여 로컬 캐싱 후 `so_survey_docs_v1`에 증거로 편입.

---

## 📜 5. 데이터 및 문서 출처와 이용 조건

| 출처 | 원천 제공자 | 라이선스 / 정책 | 프로젝트 내 활용 범위 |
|---|---|---|---|
| **Stack Overflow Developer Survey 2026** | Stack Exchange Inc. | Open Database License (ODbL) 1.0 | 기술별 실사용률, 선호도, 만족도 정형 통계 및 조사 방법론 |
| **Wikipedia REST API** | Wikimedia Foundation | CC BY-SA 4.0 / API Etiquette | 기술별 아키텍처 개요, 역사, 특징 배경 설명 문서 |
