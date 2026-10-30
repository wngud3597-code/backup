# Movie Lab 요구사항 구현·검증 현황

## UI 마무리 — 이번 확인 범위

2026-10-22 16:30 KST에 화면·입력 동작 범위를 확정했다. [범위와 검증 기록](../artifacts/review_ui_finish/implementation_report.md)의 자동 확인은 순수 표시 함수·오프라인 AppTest·**기존 실제 답변의 저장 결과 재생**이다. [최종 전체 회귀](../artifacts/review_ui_finish/final_tests.json)는 **225개·실패0·오류0**, 외부 네트워크를 차단하고 변경 완료 후 한 번 실행했다. 이는 새 실제 모델 정확도나 사용자의 직접 점검 결과가 아니다.

| 관련 항목 | UI 변경·확인 범위 | 유지·미확인 |
|---|---|---|
| F2009 영화 선택·질의응답 | 검색/선택 중심 첫 화면, 제목·연도·감독으로 구분, 영화 ID/긴 상세/줄거리는 접힘. 추천은 선택 영화 필드에서 최대 세 개이며 클릭은 입력만 채움. | 실제 선택 ID와 기존 영화별 대화 구조 유지. 사용자의 최신 직접 확인은 미실시. |
| F2008~F2009 답변·출처 | 원래 답변/번호/URL/quote/quotes는 유지하고 해당 인용의 실제 관련 행을 미리 표시. 원래 전체 인용도 별도 펼침. 영화 전환·rerun 보존을 오프라인 확인. | 출력 길이를 줄이는 생성 프롬프트나 원문 수정 없음. 과거 API 성공과 이번 표시 확인을 구분. |
| F2010 특화 | 기존 감독 표시 보완·항목별 검토·근거 부족/보류/오류 계약 유지. | 판정 계약·모델 입력·검토 모델 정확도 재검증 없음. 실제 출처 충돌 판단 등 남은 범위 유지. |
| F2011~F2012 탐색·UI | 검색 예시는 입력만 채우고 명시 검색으로 실행. 선택 영화 요약·접힌 운영 설정·단일 질문창·실제 이벤트 기반 진행 안내. | 파서·후보·가중치·색인은 그대로. 광범위 검색 품질을 새로 통과시키지 않음. |
| 관련 NF | 설치된 Streamlit 1.62.0의 기본 컴포넌트·로컬 테마·제한된 CSS 사용. KOBIS TTL0·명시 조회·독립 표시 보존. | 새 패키지·API·재임베딩·성능/비용 실험 없음. 이용 조건과 KOBIS 실제 연결 미확인 유지. |

[사용자 직접 점검표](USER_ACCEPTANCE.md)의 실제 결과는 계속 **전부 미실시**다. 자동 검사를 자기/동료 직접 점검 완료로 옮기지 않는다. 새 제출 ZIP은 사용자의 확인 후 구성한다.

## 사용자 직접 점검 — 준비·미실시

2026-10-22. 기능 개발을 종료하고 생성 `gpt-4o-mini`·검토 `gpt-5.4-mini` 정상 앱을 준비했다. [사용자 직접 점검표](USER_ACCEPTANCE.md)의 실제 결과·상태는 전부 **미실시**다. 사용자의 관측과 증거를 받은 뒤 해당 항목만 갱신한다. 서버의 무질문 health 확인은 기능/정확도/사용자 점검 통과가 아니다.

아래 실제 API·브라우저·AppTest·대체 응답 검사는 **과거 실시 시점의 증거**다. 특히 이전 Codex의 A→B→A 성공과 최신 표시의 저장 결과 재생을 이번 사용자 확인으로 바꾸지 않는다. 동료점검은 미실시다. 지정 양식은 2026-10-23 사용자 제공 배포 ZIP에서 수령을 확인하고 [작성준비본·기존 검증 결과의 구분](CHECKLIST_GUIDE.md)을 정리했다. 사본의 직접 점검 `미확인`은 아래 기능들이 모두 미구현이라는 뜻이 아니다. KOBIS는 기존 키 미설정 기록 기준 **선택 기능·실제 연결 미확인**이며, 전 질문 정확도·미측정 성능·비용을 주장하지 않는다. 이번에는 제품 코드 변경·전체 테스트 재실행·새 질문 전송·재임베딩이 없다.

## 표시 개선·누락 증거 정리 — 직전 기록

2026-10-22 14:43 KST 시작. [표시·증거 보고서](../artifacts/review_display/implementation_report.md)는 새 채팅/임베딩 0회 범위다. 생성 gpt-4o-mini·검토 gpt-5.4-mini, 판정/모델 입력/저장 스키마와 과거 출처는 유지한다. 아래의 실제 답변 검증을 다시 실행하지 않았다.

| 관련 항목 | 이번 확인 | 근거와 한계 |
|---|---|---|
| F2008~F2009 답변·출처 | 감독 메타데이터의 명확한 항목은 화면에서 ‘영화 정보 · 감독’으로 표시. 감독/상영 시간 실제 원문 행을 각각 보여주고 전체 원래 인용은 접음. | [저장 결과 재생 화면·검사](../artifacts/review_display/browser/browser_results.json). 새 모델 응답·새 정확도 검증 아님. 문법/출처가 모호하면 재분류하지 않음. |
| F2010 판정 계약 | 기존 상충/확인됨·근거 부족/검토 보류 계약 유지. 표시용 문자열만 만들며 원래 저장 본문/quote/quotes/번호/URL을 갱신하지 않음. | [관련16개 검사](../artifacts/review_display/related_tests.log), [격리 UI7개 검사](../artifacts/review_display/app_regression.log). 판정 모델·스키마/프롬프트는 수정하지 않았고 새 사실 검증은 없음. |
| F2011 조건 탐색 증거 | 기존 정확 원문·같은 벡터·양쪽 의미 후보/최종10·조건 위반·5→3위의 JSON 경로와 원본 SHA 추출. | [원본 요약](../artifacts/review_display/discovery/summary.json). 이번 새 검색/임베딩0회. 관련성 전체 개선으로 일반화하지 않음. |
| 설정·실행 증거 | 실제 기존 PS1→실제 Streamlit health200→정상 종료0→부모 두 역할 환경 복원 확인. | [실행기 증거](../artifacts/review_display/launcher/verification.json). 무질문·API0. 기존 profile_server.py 실행과 별개이며 임의 강제종료/모든 환경 조합을 시험하지 않음. |
| KOBIS·관련 NF | TTL0·새 명시 조회/일반 rerun 구분·독립 표시 유지. 이번 키 검사도 미설정/GET0. | [승인 상태 검사](../artifacts/review_display/kobis/actual_check.json). 실제 연결·수치와 이용 조건 전체 허용은 미확인 유지. |

## 검토 역할 적용·남은 검증 마무리 — 당시 기록

2026-10-22 14:27 KST에 시작했다. [이번 보고서](../artifacts/review_completion/implementation_report.md)와 [역할별 실제 출력·시간](../artifacts/review_completion/results.json)을 최신 증거로 사용한다. 기존 전체 분석·모델 비교·A→B→A를 반복하지 않았다. 아래 직전 업그레이드와 제출 기준본 표는 당시 기록으로 보존한다.

| 해당 요구 | 이번 확인 | 증거·남은 한계 |
|---|---|---|
| F2006~F2008 검색·생성·인용 | 정상 앱에서 생성 gpt-4o-mini·검토 gpt-5.4-mini로 감독/169분·같은 출처 두 구절 통과. 더 문은 질문 임베딩 502 뒤 저장 근거로 생성·인용·검토 통과. | [실제 두 화면·결과](../artifacts/review_completion/browser/browser_results.json), [SDK/원래 출력/검토](../artifacts/review_completion/browser/api_events.jsonl). 의미 검색 API 성공으로 바꾸지 않음. |
| F2010 특화 | 감독 상충과 자연위성 확인됨 두 항목을 후보 검토가 각각 수락. 원래 초안부터 두 판정이 맞았고 감독 코드 보완은 0개. | 단일 실제 혼합 질문의 확인 범위. 광범위 정확도·실제 출처 충돌 판단·기존 고정 도전 입력 전체 재검은 미실시. |
| F2011 조건 탐색 | 정확 원문 “2014년 SF 영화 중 우주 탐험을 다룬 영화”의 같은 벡터 A/B를 실제 1회 비교. 적격 15개, 의미 후보 조건 위반 3→0, 인터스텔라 최종 5→3, 최종 위반 양쪽 0. | [정확 원문 원본](../artifacts/review_completion/discovery/actual_case.json). 기존 짧은 질문 2→2와 구분. 최종 1위는 양쪽 가디언즈이며 모든 의미 조건 완성을 뜻하지 않음. |
| F2012·NF2002 안내·재사용 | KOBIS 결과 TTL 기본0. 같은 날짜 새 명시 조회는 새 요청, 일반 rerun은 현재 화면만 표시. 기존 RAG 캐시는 유지. | [정책·대체 검사 15개](../artifacts/review_completion/kobis/verification.md). 실제 키 없음/GET0이므로 실서비스 데이터·HTTP 있는 rerun은 미확인. |
| NF2001 응답 시간 | A 생성 1.609초/검토 6.753초, B 생성 2.268초/검토 7.383초를 분리 관측. | 전체 8.757초/19.243초의 단발 관측. B 검색 8.474초에는 502 실패/로컬 대체가 포함됨. 평균·일반 성능 보장 아님. |
| NF2003~NF2006 설정·오류·보존 | 기존 GMS 규약/설정 복귀 유지, 자동 낮은 모델 수락 대체 없음. 새 수집·문서 임베딩·설치·재임베딩 없음. | [보존 감사](../artifacts/review_completion/final_verification.json). KOBIS 관련15개와 영화 기록/출처/설정/RAG 보존23개 검사. 직전209개 전체 검사를 이번 실행으로 대신하지 않음. |
| NF2007 이용 조건 | 공식 약관에서 TTL 예외 근거를 확인하지 못해 재사용을 비활성화. 독립 표시·출처/약관 링크 유지. 결과를 파일·DB·LLM·RAG로 보내지 않음. | 현재 화면의 임시 세션 표시까지 포괄 허가되었다고 단정하지 않으며 전체 준수는 계속 미확인. |

F2009의 직전 실제 A→B→A 증거는 그대로 유효한 당시 기록이며 이번에 다시 시연하지 않았다. 동료점검·광범위 정확도와 전체 이용 조건의 미확인은 유지한다. 새 검토 ZIP은 만들지 않았다.

## 직전 실제 업그레이드에서 확인한 범위 — 당시 기록

2026-10-22 13:54 KST에 시작했다. 아래 갱신을 현재 상태로 적용하고, 그 뒤의 제출 기준본 표·실패 이력은 **당시 기록으로 보존**한다. [최신 전체 결과](../artifacts/review_upgrade/implementation_report.md)의 실제 브라우저/API/AppTest/대체 응답을 구분한다. 이전 179개 대신 이번 [209개·28.209초·OK](../artifacts/review_upgrade/final_tests.log), [pip check 충돌 없음](../artifacts/review_upgrade/environment.json)을 확인했다. 최초 전체 검사의 새 UI 테스트 기대값 오류는 수정·재검했고 원본 로그도 남겼다.

| 해당 요구 | 현재 확인 결과 | 최신 증거·남은 한계 |
|---|---|---|
| F2006~F2008 검색·생성·근거 | **구현 확인·대표 흐름 범위.** 실제 브라우저 A 감독/169분·같은 출처 복수 구절, B 두 판정·당시 원문/범위/수집일을 표시. B 질문 임베딩 502는 실패이며 기존 저장 근거 대체로 답변을 완성함. | [실제 이벤트](../artifacts/review_upgrade/browser/api_events.jsonl), [화면·관측 결과](../artifacts/review_upgrade/browser/browser_results.json). 의미 검색 실패를 성공으로 바꾸지 않으며 모델 검토는 진실 보증이 아님. |
| F2009 영화 선택·질의응답 | **구현 확인·이번 동일 탭 범위.** 새 정상 앱에서 A→B→A의 답변/메시지 수/구절/URL/당시 출처가 같고 모드 변경·일반 rerun 후 SDK 요청 5→5·질문 시작 2→2. | 위 브라우저 결과와 [복원 화면](../artifacts/review_upgrade/browser/03-restored.png). 과거 끊긴 세션은 당시 미확인으로 보존. 새 탭·완전 새로고침의 영구 저장은 범위 밖. |
| F2010 특화 | **일부 구현·대표 실제 판정 확인.** B의 감독 상충/자연위성 확인됨을 실제 화면에서 확인. 모델 비교는 원래 초안→감독 제안/기계 검사→검토→최종을 분리함. | [모델 실제 비교](../artifacts/review_upgrade/models/comparison.json). 고정 도전 배치에서 기준 모델 c4/c5는 오수락할 응답이었고 후보는 기대와 일치. 광범위 정확도·실제 출처 충돌 판단은 여전히 미확인. |
| F2011 조건 탐색 | **일부 구현.** `filter_catalog`→`MetadataIndex.search(...allowed_movie_ids)`→조건/ID 재검사로 연결. 제목/미지원/빈 집합 무임베딩, 조건/필드 누락/일치 없음 구분. | [A/B 원본](../artifacts/review_upgrade/discovery/ab_results.json), [설명·관련 검사](../artifacts/review_upgrade/discovery/implementation_report.md). 동일 벡터·k3·기존 키워드 조건에서 의미 후보 조건 위반 3/2/0/3→0/0/0/0, 최종 위반 양쪽 0. 기대작 최종순위 1/1/1/2 동일. 모든 자연어 조건·관련성 완성으로 보지 않음. |
| F2012·NF2002 안내·캐시 | **구현 확인·검사 범위.** 검색 버전/조건/적격 ID/전체 관련 필드/설정별 캐시, 읽은 ID도 검증. KOBIS는 폼 제출만 실행하고 성공 결과를 현재 세션 메모리에서만 재사용. | 검색 관련 검사, [KOBIS 11개 대체 검사](../artifacts/review_upgrade/kobis/tests.log), [격리 UI 재검사](../artifacts/review_upgrade/kobis_ui_after_fix.log). 실제 KOBIS 캐시·장기 운영은 미확인. |
| NF2001 응답 시간 | **대표 관측만 확인.** 준비·검색·생성·검토를 분리 기록하고 생성 노드의 겹치는 시간을 더하지 않음. | 브라우저/API 원본과 [모델 보고서](../artifacts/review_upgrade/models/implementation_report.md). 후보 Q2 검토 단발 11.454초, 기준 1.581초. 평균·일반 우열·사용성 전체 합격 수치를 만들지 않음. |
| NF2003~NF2006 키·오류·모듈·호출 | 기존 GMS 규약 유지. 역할 설정은 `GMS_GENERATION_MODEL`/`GMS_REVIEW_MODEL`, 미설정 시 기존 모델. KOBIS 별도 키·고정 오류·무자동재시도. 설치 변경 없음. | [설정](../movie_lab/config.py), [KOBIS 모듈](../movie_lab/kobis.py), [실제 호출 집계](../artifacts/review_upgrade/call_summary.json). 키 값·인증 URL·원시 예외 출력 없음. 배포/커밋 전체 보안 감사로 확대하지 않음. |
| NF2007 출처·조건 | **일부 구현·전체 준수 미확인 유지.** KOBIS 독립 표시·공개 출처·약관 링크·파일 저장 없음. 기존 TMDB/위키 조건의 미확인을 유지. | [KOBIS 공식 문서/약관 확인](../artifacts/review_upgrade/kobis/verification.md). 짧은 메모리 재사용 허용 여부도 확정하지 않음. |

KOBIS는 별도 확장 영역이며 기존 채팅 RAG 근거·자동 TMDB 매핑 완료가 아니다. [키 미설정 실화면](../artifacts/review_upgrade/kobis/missing-key-screen.png), [승인 검사](../artifacts/review_upgrade/kobis/actual_check.json)는 실제 데이터 GET 0회다. 실제 수치·실서비스 캐시 재사용은 미확인이다. 동료점검은 계속 미실시다.

## 아래는 제출 기준본 당시 통합 기록

기준일: 2026-10-22. 최신 기준은 [감독 필드 보완 보고서][director-report]와 그 실제 실행 원본이다. 이 문서는 기존 코드와 증거를 읽어 통합했으며, 작성 과정에서 API·설치·테스트·브라우저·ZIP을 실행하지 않았다. 요구사항명은 PDF 9~10쪽을 확인한 [원문 명칭 기록][reference]을 그대로 사용한다. 과거 단계의 요약 명칭이나 배점은 사용하지 않는다.

현재 기록상 메타데이터는 964건, 외부 문서는 314개 ready 청크다. 문서·질문 임베딩은 `text-embedding-3-small`/1536차원, 채팅은 설정 가능한 `GMS_CHAT_MODEL`의 기본값 `gpt-4o-mini`를 사용한다. 최신 실제 서버 보고 모델은 `gpt-4o-mini-2024-07-18`이다. [저장소 전후 기록][store-after]에서 건수·전체 내용·벡터 해시가 같으며, 최근 보완에서 전체 재색인·재임베딩을 하지 않았다. 최신 전체 회귀 **179개·24.860초·OK**와 의존성 충돌 없음은 [기존 검사 로그][final-tests]와 [환경 기록][environment]의 결과다. 이 문서에서 재실행한 결과가 아니다.

## 상태와 증거를 읽는 방법

- **구현 확인:** 아래에 적은 코드·사례 범위에서 동작을 확인했다. 모든 질문의 정확도나 요구사항 전체의 무조건 합격을 뜻하지 않는다.
- **일부 구현:** 기능은 있으나 지원 범위나 확인 범위가 제한되어 있다.
- **실행 검증 필요:** 코드·일부 관측은 있어도 해당 요구를 판단할 실행 증거가 부족하다. `미구현`과 구분한다.
- **실제 API/CLI:** 실제 GMS·검색·저장소를 사용한 실행이다. 브라우저 성공을 대신하지 않는다.
- **실제 브라우저:** 실제 앱·SDK 응답을 화면에서 관측했다. **AppTest·대체 응답·저장 결과 재생**은 별도로 표시하며 실제 모델 정확도나 새 API 성공으로 계산하지 않는다.

## 필수 기능 F2001~F2012

| 코드 · 원문 요구사항명 | 상태 | 구현 파일·함수 | 실제 확인 결과와 원본 증거 | 미확인·제한 |
|---|---|---|---|---|
| **F2001 항목 메타데이터 적재** | 구현 확인 | [data.py](../movie_lab/data.py) `load_movies`, `Movie`, `build_index_text`; [app.py](../app.py) `load_catalog` | 실제 964건의 적재·문자열 ID·유일성·필드 정규화는 [초기 저장 보고][index-report]에 기록되어 있다. 최신 [저장소 전후 검사][store-after]도 메타데이터 964건과 내용 보존을 확인했다. 경로 오류·잘못된 JSON·빈 감독·누락 값은 오프라인 회귀 범위다. | 964는 현재 데이터의 확인 건수이며 앱의 고정 개수가 아니다. 데이터에 없는 사실이나 인물 식별자를 보충한 것은 아니다. |
| **F2002 메타데이터 색인(RAG 1)** | 구현 확인 | [index.py](../movie_lab/index.py) `IndexConfig`, `MetadataIndex.index_movies`, `verify_movies`, `search`, `get_movie_source`; [embeddings.py](../movie_lab/embeddings.py) `GmsEmbeddings` | **실제 API/CLI:** 소량 3건 성공 후 [전체 색인][full-index]은 3→964건, 나머지 961건 임베딩·16요청이었다. 이후 [별도 프로세스 재조회][full-verify]로 964건을 확인하고, [동일 데이터 재실행][rerun-index]에서 964→964·추가 0·재임베딩 0이었다. 안정 ID `meta:{movie_id}`와 모델·차원·텍스트 버전별 컬렉션을 사용한다. 최신 [해시 검사][store-after]도 보존 확인. | 저장 정합성과 검색 관련성은 별개다. 이 항목으로 F2011이나 광범위 검색 품질을 완료 처리하지 않는다. |
| **F2003 검색어 추출(프롬프트1)** | 구현 확인 · 대표 준비 사례 범위 | [document_llm.py](../movie_lab/document_llm.py) `LlmDocumentPlanner.extract`; [extract_queries.txt](../prompts/extract_queries.txt); [document_pipeline.py](../movie_lab/document_pipeline.py) `DocumentPipeline.prepare` | **이전 실제 API:** [실시간 인터스텔라 준비][interstellar-prepare]와 [스냅샷 더 문 준비][moon-prepare]에서 선택 영화·질문·최근 대화를 입력해 검색어를 만들고 `json_schema` 응답을 검사했다. 영화 자체 검색어는 코드에서 포함한다. 처음 주제어를 놓친 [실패 원본][interstellar-initial]과 수정 후 결과를 모두 보존한다. | 최신 감독 재확인은 준비 캐시 hit이므로 새 검색어 추출 검증이 아니다. 모든 질문에서 주제를 충분히 추출한다는 정확도 평가는 없다. 사용자 주장·이전 답변은 검증 사실이 아니다. |
| **F2004 외부 문서 수집(프롬프트2)** | 일부 구현 | [document_llm.py](../movie_lab/document_llm.py) `LlmDocumentPlanner.select`; [select_documents.txt](../prompts/select_documents.txt); [wiki.py](../movie_lab/wiki.py) `WikiClient.search`, `fetch_page`, `SnapshotRepository`; [document_pipeline.py](../movie_lab/document_pipeline.py) `prepare` | **이전 실제 API:** 인터스텔라 실시간 4문서와 더 문 스냅샷 3문서의 선별·본문 수집을 각각 [실시간 기록][interstellar-prepare]·[스냅샷 기록][moon-prepare]으로 확인했다. 2023년 더 문에 잘못 연결된 2009년 자체 문서는 제외했다. 스키마·후보 ID 오류, 빈 본문, 연락처 없음·외부 실패 대체는 **대체 객체 검사**다. | 인터스텔라 자체 문서의 놀란/놀런 표기는 식별 `확인 필요`였다. 보편적인 동명·별칭 식별, 모든 질문의 후보 관련성, 실제 장애에서 자동 스냅샷 전환은 미확인이다. 스냅샷 사용은 실시간 성공이 아니다. |
| **F2005 외부 문서 색인(RAG 2)** | 구현 확인 · 선택 영화 준비 범위 | [external_index.py](../movie_lab/external_index.py) `ChunkConfig`, `chunk_document`, `ExternalIndex.index_documents`, `search`, `ready_documents` | **이전 실제 API/저장:** 문단·문장 청킹, 메타데이터와 별도 컬렉션, 영화·문서·본문 해시·청킹 버전별 청크 ID를 사용했다. 두 영화의 저장·재조회·격리·캐시 재사용은 [준비/색인 보고][stage3-report]와 [격리 원본][isolation]에 있다. 최신 [읽기 전용 검사][store-after]는 전체 314개 청크가 ready이고 내용·벡터 해시가 불변임을 확인했다. | 최초 78/44청크는 당시 두 준비 결과이며 현재 314개 전체 건수와 혼동하지 않는다. 부분 실패·재개·새 저장 성공 뒤 구청크 정리는 임시 저장소 회귀로 확인했다. 전체 영화 외부 자료 일괄 수집은 하지 않는다. |
| **F2006 근거 검색 및 병합** | 구현 확인 · 대표 경로 범위 | [rag.py](../movie_lab/rag.py) `MovieRag._retrieve`; [retrieval.py](../movie_lab/retrieval.py) `EvidenceRetriever.retrieve`, `_metadata_source`; [external_index.py](../movie_lab/external_index.py) `search`, `ready_documents` | **최신 실제 API/CLI:** [감독 재확인][director-actual]에서 `retrieve → generate`, 선택 영화 메타데이터의 김용화와 배경 문서의 자연위성 구절을 함께 확보했다. 선택 `movie_id`·ready 필터, 로컬 BM25 후보, 문서별 상한·중복/문맥 제한을 적용한다. **이전 실제 브라우저:** B 질문 임베딩 502 후 저장 청크의 키워드 보완으로 두 근거를 확보했으나 의미 검색 자체는 실패했다. [당시 원본][browser-events], [502 대체 회귀][retrieval-tests]를 구분한다. | 검색된 원문이 질문 전체를 충분히 덮는다는 보장은 없다. 최신 정상 검색 성공이 과거 502를 지우거나 모든 장애 복구를 검증하지 않는다. 현실 배경을 영화 장면의 근거로 확정하지 않는다. |
| **F2007 근거 기반 답변 생성(프롬프트3)** | 구현 확인 · 대표 일반/혼합 질문 범위 | [rag.py](../movie_lab/rag.py) `MovieRag._generate`; [answering.py](../movie_lab/answering.py) `AnswerGenerator.generate`, `materialize_citations`, `validate_answer`, `_review_verify`; [generate_answer.txt](../prompts/generate_answer.txt) | **실제 브라우저:** 인터스텔라 감독·169분 일반 답변과 두 구절 표시 성공. **최신 실제 API/CLI:** 감독 근거 부족 초안에 제한된 메타데이터 제안을 적용하고 기존 묶음 검토를 거쳐 두 항목을 수락했다. [브라우저 보고][browser-report], [최신 실제 입력·출력·감사][director-actual] 참조. 무인용 근거 부족은 이전 [실제 3사례][fix-actual]에 있고, 잘못된 JSON·인용·검토 실패는 회귀로 구분한다. | 광범위 답변 정확도·문법·모든 후속 질문의 충분성은 미확인이다. 코드 형식 검사와 같은 모델의 의미 검토는 진실·완전성 보증이 아니다. 최신 성공은 CLI이며 수정 후 새 브라우저 성공은 아니다. |
| **F2008 근거 표시** | 구현 확인 · 관측한 인용 범위 | [answering.py](../movie_lab/answering.py) `materialize_citations`, `validate_answer`; [evidence.py](../movie_lab/evidence.py) `cited_sources`, `source_caption`, `source_quotes`; [app.py](../app.py) `render_sources`; [state.py](../movie_lab/state.py) `append_assistant_message` | **실제 브라우저:** A의 같은 `[근거 1]`에 떨어진 감독·상영 시간 원문 두 구절과 URL을 표시했다. B는 실제 인용한 배경 문서·스냅샷·2026-09-10만 표시했다. [A 실제 화면][screen-a], [B 당시 화면][screen-b], [원본 관측][browser-events] 참조. 최신 CLI도 [감독 행·달 구절과 번호 대응][director-actual]을 확인했다. 원문 없는 두 번째 구절·번호 오류·과거 `quote/quotes` 보존은 회귀다. | 화면의 원문 링크를 열어 현재 외부 페이지와 다시 대조한 검사는 하지 않았다. 출처 번호 형식·원문 포함 검사와 주장·근거 의미 일치는 별도이며 전 출처의 정확도를 보증하지 않는다. |
| **F2009 항목 선택 및 질의응답** | 실행 검증 필요 · 코드/회귀와 일부 실제 흐름 확인 | [app.py](../app.py) `select_discovered_movie`, `on_movie_change`, 채팅 입력/재답변; [state.py](../movie_lab/state.py) `get_thread`, `append_user_message`, `append_assistant_message`, `build_payload`; [rag.py](../movie_lab/rag.py) `recent_history` | **실제 브라우저:** 자연어 탐색 결과에서 제목·연도·감독·ID가 맞는 A 선택, 실제 질문, 새 세션 B→A→B와 rerun 시 B 기록·출처 보존은 [원본 결과][browser-results]에 있다. **AppTest:** 영화별 기록, 답변별 `answer_id/content/sources`, A→B→A·rerun·재답변 중 질문 중복 방지는 [관련 UI 로그][ui-tests]와 [최신 회귀][final-tests]에 있다. | **원래 A 답변을 동일 세션 A→B→A로 복원한 최신 실제 브라우저 증거는 없다.** 도구 timeout으로 첫 세션이 종료됐고 답변 주입·A 재전송을 하지 않았다. 새 세션 B 복원·옛 실습 단계·AppTest를 원래 A 복원 성공으로 바꾸지 않는다. 완전 새로고침 뒤 영구 저장은 범위 밖이다. |
| **F2010 도메인 특화 기능** | 일부 구현 · 제한된 실제 혼합 질문 성공 | [answering.py](../movie_lab/answering.py) `prepare_verify_items`, `apply_verify_review`, `_review_verify`; [director_check.py](../movie_lab/director_check.py) `propose_director_checks`; [review_verify.txt](../prompts/review_verify.txt) | 작품 속 묘사/현실 사실과 확인됨/근거와 상충/근거 부족/출처 충돌을 구분한다. **최신 실제 API/CLI:** [지정 질문 1회][director-actual]에서 c1 감독 상충·c2 자연위성 확인됨, 생성 1회+묶음 검토 1회, 검토 2/수락 2/보류 0. **대체 응답:** 제안 반려 시 c1만 검토 보류, c2·기존 번호 보존은 [저장 실패 재생][director-offline]과 [관련 회귀][director-tests]로 확인했다. | **실제 출처 충돌 판정은 미확인**이다. 네 관계의 대체 응답 검사는 실제 모델 판정 정확도 평가가 아니다. 감독 보완은 단일 감독·명확한 긍정 명제·정확한 표기·선택 ID/실제 감독 행에 한정하며 별칭·번역·복수 감독·짧거나 유사한 이름은 기권한다. 이름 레지스트리는 전세계 인물 ID가 아니다. |
| **F2011 조건 기반 항목 탐색** | 일부 구현 | [discovery.py](../movie_lab/discovery.py) `parse_conditions`, `_matches`, `semantic_query`, `discover_movies`; [services.py](../movie_lab/services.py) `search_catalog`; [app.py](../app.py) `select_discovered_movie` | **이전 실제 임베딩 검색:** 같은 대표 3질문의 기대작 순위 5/8/46→1/1/1, 조건 검증·키워드 결합 결과는 [실제 비교][discovery-actual]에 있다. 정확한 제목/원제·연도·감독·장르·동명 구분·결과 없음과 미지원 필드 안내를 구현했다. **현재 실제 브라우저:** 다른 2014/SF/우주 탐험 질문에서 인터스텔라 5위 후보 선택. **오프라인 실제 데이터 검사:** 부정·숫자 경계 수정은 [결함 전후][defects]와 회귀에 있다. | 서로 다른 질문의 1위와 5위를 같은 비교로 다루지 않는다. 의미 검색 순위는 명시 조건 충족 증거가 아니다. 데이터에 없는 조건·지원 밖 부정/복합 문법은 검증 불가이며 자유로운 모든 조건·광범위 검색 정확도는 미확인이다. |
| **F2012 진행 상태 및 안내** | 구현 확인 · 최신 표시 일부는 회귀/재생 확인 | [app.py](../app.py) 자료 준비 단계, `st.status`, 답변 밖 안내·재답변; [document_pipeline.py](../movie_lab/document_pipeline.py) `prepare(progress=...)`; [rag.py](../movie_lab/rag.py) `_announce` | 준비/검색/생성·오류와 선택 영화·현재 모드를 표시한다. 전체 부족·일부 부족·일부/전체 검토 보류·API 실패를 구분한다. 일부 근거 부족과 검색 연결 실패는 접힌 진행 영역 밖에 안내한다. **AppTest:** [UI 7개 검사][ui-tests]. **저장 결과 재생:** [최신 상태 화면][screen-replay]과 [재생 기록][browser-replay]. | 실제 B 원본 화면은 상태 안내 수정 전이며 [당시 실패][browser-report]를 보존했다. 최신 표시 화면은 배너가 있는 API 없는 재생이고 새 실제 질문 성공 증거가 아니다. 모든 장애 상황의 실제 화면 관측은 없다. |

## 비기능 NF2001~NF2007

| 코드 · 원문 요구사항명 | 상태 | 구현 파일·함수 | 실제 확인 결과와 원본 증거 | 미확인·제한 |
|---|---|---|---|---|
| **NF2001 응답 시간** | 실행 검증 필요 · 대표 시간만 실측 | [rag.py](../movie_lab/rag.py) `retrieval_observation`, `generation_observation`; [answering.py](../movie_lab/answering.py) `_request` | **최신 실제 CLI:** 준비 1.254초·검색 3.017초·생성 요청 11.437초·검토 요청 1.885초·전체 17.858초. 준비 hit·문서 임베딩 0·질문 임베딩 1·채팅 2를 [원본][director-actual]에 함께 기록했다. **이전 실제 브라우저:** A 서비스 4.396초/브라우저 5.574초, B 12.485초/13.527초이며 B에는 502가 포함된다. [당시 기록][browser-report] 참조. | 원문은 대표 질문의 전체 시간이 사용에 지장 없어야 한다는 요구이며 **합격 초수는 없다**. 단발 관측을 사용성 합격·평균·최악 시간으로 확정하지 않는다. `generation_node`는 생성/검토와 겹쳐 다시 더하지 않는다. |
| **NF2002 수집 캐시** | 구현 확인 · 확인한 성공/갱신 경로 범위 | [document_pipeline.py](../movie_lab/document_pipeline.py) `SuccessCache.get/put`, `DocumentPipeline._body/prepare`; [external_index.py](../movie_lab/external_index.py) `index_documents` | **실제 준비 재실행:** [인터스텔라 hit][interstellar-cache]·[더 문 hit][moon-cache]에서 chat/wiki/문서 임베딩 0. **최신 실제 CLI:** 준비 hit·본문 3건·준비 외부 호출 0, 답변 생성은 새 요청이었다. 질문별 선별과 문서별 최신 본문 분리, A 갱신 뒤 B가 구본문을 되살리지 않는 검사는 [결함 재현][defects]와 [최신 회귀][final-tests]의 **대체 응답/임시 저장소 검사**다. | 실패·빈 결과는 성공으로 영구 캐시하지 않는다. 모든 TTL 경계·실제 서비스 장기 운영·실제 장애 복구를 측정한 것은 아니다. 과거 답변의 출처 스냅샷은 캐시 갱신 대상이 아니다. |
| **NF2003 API 키 관리** | 일부 구현 · 로컬 경로 확인 | [document_llm.py](../movie_lab/document_llm.py) `create_document_planner`; [embeddings.py](../movie_lab/embeddings.py) `create_gms_embeddings`; [answering.py](../movie_lab/answering.py) `create_answer_generator`; [.gitignore](../.gitignore) | **환경변수:** 명시적 클라이언트 실행 시 기존 `load_dotenv(..., override=False)`→`GMS_KEY`→기존 GMS 주소를 사용한다. 실제 호출은 [최신 원본][director-actual]에 있으나 키 값은 기록하지 않는다. **커밋/배포물 보호:** [이전 git check-ignore/추적 상태 확인 기록][stage3-report]과 [최신 ZIP 제외 검사][package-result]는 별개 증거다. `.env`, 키, 가상환경·저장소·전체 배포 데이터 제외를 확인했다. | 환경변수 사용만으로 커밋 보호를 입증하지 않는다. 이전 Git 검사는 당시 상태이며 이 문서 작성 중 최신 추적 상태·커밋 전체를 다시 감사하지 않았다. 배포 환경·키 수명/권한 전체는 미확인이다. 실제 키 내용 대조는 하지 않는다. |
| **NF2004 내부 정보 비노출** | 일부 구현 · 확인한 오류/검토 경로 범위 | [embeddings.py](../movie_lab/embeddings.py) `failure_details`, `quiet_sdk_logging`; [document_pipeline.py](../movie_lab/document_pipeline.py) `safe_error`; [wiki.py](../movie_lab/wiki.py) `WikiError`; [answering.py](../movie_lab/answering.py) `_request_impl` | **실제 브라우저:** 502를 짧은 분류·상태로 기록했다. **대체 응답:** 인증/지원/timeout·잘못된 JSON·의미 검토 반려·실패 단계 보존은 [최신 회귀][final-tests]와 [오프라인 재생][director-offline]에 있다. 검토 보류는 원래 미수락 이유·인용을 정상 답변처럼 노출하지 않는다. [최신 패키지 검사][package-result]에서 비밀 파일 제외·일반 자격증명 형태 검사 통과. | 임의 입력·예외에 포함될 수 있는 모든 비밀정보를 탐지한다는 보증이나 전체 보안 인증이 아니다. 원시 헤더·예외 본문·트레이스백은 사용자에게 노출하지 않는 경로로 제한한다. |
| **NF2005 모듈 분리** | 구현 확인 | [data.py](../movie_lab/data.py) 적재; [discovery.py](../movie_lab/discovery.py) 탐색; [document_llm.py](../movie_lab/document_llm.py)/[wiki.py](../movie_lab/wiki.py)/[document_pipeline.py](../movie_lab/document_pipeline.py) 준비; [index.py](../movie_lab/index.py)/[external_index.py](../movie_lab/external_index.py) 저장; [retrieval.py](../movie_lab/retrieval.py)/[rag.py](../movie_lab/rag.py)/[answering.py](../movie_lab/answering.py) 검색·그래프·답변; [state.py](../movie_lab/state.py)/[evidence.py](../movie_lab/evidence.py) 기록·출처 | 현재 모듈은 실제 앱·CLI·회귀에서 사용하는 역할별 구현이다. 감독 제안은 [director_check.py](../movie_lab/director_check.py)에 분리하되 기존 원문 검사·항목 검토를 통과해야 한다. [최신 변경·보존 범위][director-report]와 [보존 파일 해시][store-after] 참조. 대화/답변 출처 원본은 assistant 메시지 한 곳이다. | 모듈 분리는 모델 품질·보안·영구 대화 저장의 보증이 아니다. 미래 기능을 위한 빈 모듈·별도 프론트엔드는 추가하지 않았다. |
| **NF2006 외부 API 예절** | 구현 확인 · 실제 일반 수집/오프라인 오류 범위 | [wiki.py](../movie_lab/wiki.py) `resolve_user_agent`, `WikiClient._request`, `_retry_delay`, `_wait_before_retry`; 각 GMS 클라이언트 생성 함수 | **이전 실제 위키 API:** [실시간 수집][interstellar-prepare]과 [보고][stage3-report]의 요청 식별정보·12초 timeout·직렬 호출·간격·제한 재시도. GMS는 SDK 자동 재시도 0이며 실제 호출 수를 남긴다. `Retry-After` 초/HTTP 날짜와 대기 상한 초과 시 조기 재요청 금지는 [결함 전후][defects]·[회귀][final-tests]의 **대체 응답 검사**다. | 실제 429/모든 5xx/HTTP 날짜 대기를 고의 발생시켜 검증하지 않았다. 연락처 없음·호출 제한 시 대체 경로의 실제 서비스 장애 검증은 미확인이다. 연락처 값은 로그·검토 묶음에 포함하지 않는다. |
| **NF2007 출처와 이용 조건** | 일부 구현 · 전체 준수 미확인 | [evidence.py](../movie_lab/evidence.py) `source_caption`; [app.py](../app.py) `render_sources`; [external_index.py](../movie_lab/external_index.py) 출처 메타데이터; [출처·이용 조건 기록][conditions] | 제목·원문 URL·메타데이터/실시간/스냅샷·수집 시점을 보존·표시한다. 제공 README와 당시 공식 약관 확인 범위, 위키백과 유래 발췌의 기여자/원문 링크·CC BY-SA 4.0·처리 내역은 [기존 확인 기록][conditions]에 있다. 실제 화면은 [A][screen-a]/[B][screen-b] 참조. 이번 문서 작업에서 약관을 다시 조회하지 않았다. | **TMDB 메타데이터의 별도 재배포 허락·권리 범위, 개별 문서의 예외/추가 표시 조건은 미확인**이다. 원문 링크 표시나 전체 데이터 ZIP 제외만으로 전체 이용 조건 준수·공개 배포 가능을 확정하지 않는다. |

## 실패와 수정 후 성공의 시점

| 단계 | 증거 유형 | 당시 결과와 현재 해석 |
|---|---|---|
| Stage4_fix | 실제 API/CLI | [당시 3사례][fix-actual]의 혼합 질문은 맞는 감독/자연위성 초안·구절 뒤 전역 의미 검토가 거부해 최종 실패했다. 이후 성공으로 덮어쓰지 않는다. |
| Stage4_items | 실제 API/CLI + 별도 대체 응답 계약 검사 | 검토를 항목별 관계로 바꾼 뒤 [당시 지정 1회][items-actual]는 두 항목 수락에 성공했다. [오프라인 네 조합][items-offline]은 관계 응답에 따른 코드 동작 검사이며 모델 정확도 증거가 아니다. |
| 브라우저 통합 시연 | 실제 Chrome/SDK | [당시 원본][browser-events]에서 A 일반 답변은 성공했지만 B는 502 후 저장 근거를 확보해도 **생성 초안**이 감독을 근거 부족으로 작성했다. c2만 검토한 `item_review_passed`를 두 주장 모두 성공으로 보지 않는다. 원래 A 복원은 도구 세션 종료로 미확인이다. |
| 브라우저 시연 뒤 안내 보완 | AppTest + 저장 결과 재생 | [최신 표시 재생][browser-replay]은 부분 근거 부족·검색 연결 실패 안내를 확인한 것이다. [세 번째 화면][screen-replay]에는 검증용/API 없음 배너가 있으며 새 실제 응답이나 수정 후 브라우저 성공을 뜻하지 않는다. |
| 감독 필드 보완 · 최신 | 실제 API/CLI 1회 + 별도 대체 응답 재생 | [최신 원본][director-actual]의 초안도 c1 근거 부족이었다. 선택 메타데이터의 실제 감독 행으로 **검토용 제안**을 만들고 c1/c2를 같은 검토에 전달해 상충/확인됨을 수락했다. 자동 수락·판정 강제·추가 검토·전체 질문 재시도는 없었다. [저장 실패 재생][director-offline]과 실제 모델 실행은 구분한다. |

따라서 현재 결론은 **“제한된 감독 필드 보완 후 지정 혼합 질문의 실제 CLI 성공”**이다. 과거 브라우저 실패가 사라진 것도, 최신 전체 브라우저 통합 시연이 완료된 것도 아니다. **원래 A→B→A, 광범위 정확도, 실제 출처 충돌 판정, 전체 이용 조건 준수**는 계속 미확인이다. 감독 필드의 문자열 목록에는 인물/크레딧 ID가 없다는 [구조 확인][director-structure]도 이 제한의 근거다.

## 선택 요구사항

**F2013~F2016은 별도 미판정**이다. 필수/비기능 항목의 구현을 선택 요구사항의 완료·배점으로 전환하지 않으며, 선택 기능·모델 비교·추가 실제 호출을 이번 문서 작업에서 수행하지 않았다.

## 검토 묶음에서 필요한 원본 증거

이 문서는 저장소의 원본 파일을 상대 링크한다. 검토 ZIP에서 링크를 유지하려면 아래 참조 정의가 가리키는 원본 경로를 그대로 포함해야 한다. 소스 링크 대상인 `app.py`, `movie_lab`, `prompts`, `.gitignore`도 같은 상대 구조가 필요하다. 원본을 수정·축약본으로 교체하거나 과거 실패를 삭제하지 않는다. 키·`.env`·가상환경·Chroma 저장소·전체 배포 데이터는 포함하지 않는다. 기존 ZIP에 이 새 문서와 모든 과거 증거가 이미 들어 있다고 주장하지 않으며, 이번에는 패키징을 실행하지 않았다.

[reference]: ../artifacts/review_stage4/requirements_reference.md
[director-report]: ../artifacts/review_director_field/implementation_report.md
[director-actual]: ../artifacts/review_director_field/actual_case.json
[director-offline]: ../artifacts/review_director_field/offline_cases.json
[director-tests]: ../artifacts/review_director_field/related_tests.log
[retrieval-tests]: ../artifacts/review_director_field/retrieval_tests.log
[director-structure]: ../artifacts/review_director_field/director_field_structure.json
[store-after]: ../artifacts/review_director_field/store_after.json
[final-tests]: ../artifacts/review_director_field/final_tests.log
[environment]: ../artifacts/review_director_field/environment.json
[package-result]: ../artifacts/review_director_field/package_result.json
[conditions]: ../artifacts/review_director_field/source_conditions.md
[index-report]: ../artifacts/review/implementation_report.md
[full-index]: ../artifacts/review/full_index.jsonl
[full-verify]: ../artifacts/review/full_verify.jsonl
[rerun-index]: ../artifacts/review/rerun_index.jsonl
[stage3-report]: ../artifacts/review_stage3/implementation_report.md
[discovery-actual]: ../artifacts/review_stage3/discovery_actual.json
[interstellar-initial]: ../artifacts/review_stage3/interstellar_initial.json
[interstellar-prepare]: ../artifacts/review_stage3/interstellar_prepare.json
[moon-prepare]: ../artifacts/review_stage3/moon_prepare.json
[interstellar-cache]: ../artifacts/review_stage3/interstellar_cached.json
[moon-cache]: ../artifacts/review_stage3/moon_cached.json
[isolation]: ../artifacts/review_stage3/isolation_and_reuse.json
[defects]: ../artifacts/review_stage4/defect_fixes.json
[fix-actual]: ../artifacts/review_stage4_fix/actual_cases.json
[items-actual]: ../artifacts/review_stage4_items/actual_case.json
[items-offline]: ../artifacts/review_stage4_items/offline_contract.json
[browser-report]: ../artifacts/review_browser_demo/implementation_report.md
[browser-events]: ../artifacts/review_browser_demo/api_events.jsonl
[browser-results]: ../artifacts/review_browser_demo/browser_results.json
[ui-tests]: ../artifacts/review_browser_demo/related_ui_tests.log
[browser-replay]: ../artifacts/review_browser_demo/browser_replay.json
[screen-a]: ../artifacts/review_browser_demo/01-interstellar.png
[screen-b]: ../artifacts/review_browser_demo/02-moon-verification.png
[screen-replay]: ../artifacts/review_browser_demo/03-status-replay.png
