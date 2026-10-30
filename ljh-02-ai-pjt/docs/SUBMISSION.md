# 제출 구성과 남은 확인

기준일: 2026-10-22. 기능 개발을 종료하고 **사용자 직접 검증 준비 → 실제 결과 반영 → 최신 제출 ZIP 구성** 순서로 진행한다. 현재 [직접 점검표](USER_ACCEPTANCE.md)의 실제 결과는 전부 미실시다. 아직 최종 제출 ZIP을 만들지 않았으며 **제출·업로드·Git push도 수행하지 않았다.** 기존 검토 ZIP과 수업 제출 ZIP은 용도와 이름이 다르다.

2026-10-23 양식 수령 반영: 사용자 제공 `체크리스트_배포용.zip`에서 같은 양식의 XLSX/PDF를 확인하고 [셀프·상호 작성준비본과 작성 안내](CHECKLIST_GUIDE.md)를 준비했다. **사용자·동료의 실제 점검은 아직 미실시**이며 기존 API/테스트 결과는 과거 증거로만 유지한다.

2026-10-23 파일 정리: 현재 파일을 복사한 **`제출용_최신본/`**을 별도로 준비하고, 불필요한 이전 ZIP·변경 전 복제본·임시 개발 자료는 **`제출제외_개인보관/`**에 원래 경로와 해시를 기록해 이동한다. 삭제하지 않는다. 현재 앱의 `venv`·키 설정·데이터/색인·Git·브라우저 환경은 원위치에 유지하고 제출용 복사본에는 포함하지 않는다. **제출 대상은 `streamlit_lab` 전체가 아닌 제출용 폴더의 내용**이다. 실제 셀프/동료 결과와 최종 파일명 확인은 별도로 남아 있으며 이번에 ZIP·외부 제출을 수행하지 않는다.

**최신 사용자 지시에 따라 발표는 없고 원고·슬라이드 작업은 종료했다.** 발표 시간 측정이나 새 PPT 제작은 제출 전 남은 작업이 아니다. 기존 원고는 역사 자료로만 보존하며 자기/동료 점검·제출 요구와 미확인 브라우저 확인은 유지한다.

## 수업 원문에서 확인한 요구

제공 요구사항 PDF의 18~23쪽을 확인한 [원문 위치·해석 기록](../artifacts/review_submission_baseline/pdf_submission_reference.md)과 이번 [제출 메타정보 재확인](../artifacts/submission_preparation/pdf_metadata.md)을 근거로 한다. 제출 지침을 새로 만들거나 미확인 배점·점수를 붙이지 않는다.

- 산출물은 Git README 또는 Word/PowerPoint로 정리해 `lab.ssafy.com`에 제출한다. 이는 문서 정리 매체의 선택이며 발표를 요구한다는 뜻은 아니다. 별도 PPT 제작은 이번 작업에 포함하지 않는다.
- 프로젝트 요구사항 정의, RAG 설계, 구현 소스·수집/색인 스크립트, README, 기능/NF 대조표·검증 결과·셀프/상호 체크리스트와 필요한 화면을 포함한다.
- “4장의 확인 항목별 실행 결과 화면”은 **PDF 제4장 검증 항목**을 가리키며 스크린샷 네 장이라는 뜻이 아니다. 필요한 항목의 증거를 연결해야 한다.
- 수업 ZIP 이름은 `AI코어프로젝트2_[주제명]_지역_반_성명.zip`이다. PDF의 지역·반·성명은 **자리표시자**이며 실제 개인 정보가 기입된 것은 아니다. 제출처는 `lab.ssafy.com`으로 확인되지만 구체적인 최종 제출 날짜·시각은 확인되지 않았다. 1일차 16시는 도메인 확정 시점이며 제출 마감으로 쓰지 않는다. 영화 팩의 `Movie Lab`도 개인 주제명을 강제하는 값이 아니다.
- 체크리스트는 2026-10-23 사용자 제공 배포 ZIP으로 수령을 확인했다. 엑셀의 작성 안내에는 **3일차 셀프 15:30~16:30, 상호 16:30~17:30**이 명시되어 있다. 이는 점검 일정이며 최종 제출 마감은 별도로 확인해야 한다. XLSX/PDF를 모두 제출해야 하는지는 이 ZIP만으로 확인되지 않았다.

## 현재 파일과 제출 요구의 대응

| 수업 제출 항목 | 준비된 실제 파일 | 준비 상태·남은 일 |
|---|---|---|
| 프로젝트 요구사항 정의 | [통합 대조표](REQUIREMENTS.md), [README](../README.md), [질문 예시](PRESENTATION.md) | 도메인 영화, 현재 항목 964건, 필수/NF 구현·미확인, 출처/조건, 실제 질문 예시를 연결했다. 선택 F2013~F2016은 별도 미판정이다. 별도 수업 양식이 있다면 옮겨야 한다. 제공 PDF 원본만을 개인 요구사항 정리본으로 간주하지 않는다. |
| RAG 파이프라인 설계 | [README의 데이터 흐름·계약](../README.md#데이터-흐름과-설계-이유) | 두 컬렉션/필드, 수집·청킹·색인·병합, 3개 프롬프트 역할/출력, 인용·특화·캐시·오류 경로를 설명했다. 900/120·Top-k 6 등의 설계 이유는 기록했으나 값별 실측 비교는 미실시다. |
| 문제와 해결 과정 | [통합표의 실패→수정 시점](REQUIREMENTS.md#실패와-수정-후-성공의-시점), [감독 보완 결과](../artifacts/review_director_field/implementation_report.md) | 전역 검토 오거부와 감독 정보 활용 누락을 다른 원인으로 구분했다. 과거 브라우저 실패는 보존했다. |
| 소스와 실행 방법 | [app.py](../app.py), [movie_lab](../movie_lab), [prompts](../prompts), [의존성](../requirements-project.txt), [.env.example](../.env.example) | 현재 기준본을 포함한다. 실습 `step0`~`step8`, `plus_widget_key.py`, `requirements.txt`도 보존한다. 비밀키는 수신자가 별도로 설정해야 한다. |
| 수집·색인 스크립트 | [prepare_documents.py](../scripts/prepare_documents.py), [index_metadata.py](../scripts/index_metadata.py), [search_metadata.py](../scripts/search_metadata.py) | 코드·명령 안내 준비. 전체 외부 문서 일괄 수집은 지원/실행하지 않는다. 과거 검증 명령은 당시 기록이지 이번 실행이 아니다. |
| 테스트 결과표·실행 증거 | [통합표](REQUIREMENTS.md), [이번 UI 최종 전체225개](../artifacts/review_ui_finish/final_tests.log), [UI 관련19개](../artifacts/review_ui_finish/ui_related_tests.log), [당시 환경/pip check](../artifacts/review_upgrade/environment.json) | 이번 UI 변경 완료 후 전체 오프라인 회귀 한 번·225개 OK. 과거 표시16/UI7·전체209개는 당시 증거다. 실제 API·브라우저·AppTest·대체 응답과 과거 실패를 구분한다. 패키지 변경·pip check 재실행 없음. |
| 최신 실제 질문 화면 | [현재 모델 프로필 A 일반](../artifacts/review_completion/browser/01-interstellar.png), [B 특화](../artifacts/review_completion/browser/02-moon.png), [원래 출력·검토·시간](../artifacts/review_completion/results.json) | 과거 Codex의 정상 앱 실제 두 질문이다. 생성4o-mini·검토5.4-mini. B 질문 임베딩502 실패와 저장 근거 대체 성공을 구분한다. 이번 사용자 직접 확인 결과는 아니다. |
| 최신 UI 화면 | [첫 화면](../artifacts/review_ui_finish/01-first-screen.png), [선택 후](../artifacts/review_ui_finish/02-movie-selected.png), [답변/근거](../artifacts/review_ui_finish/03-answer-and-evidence.png), [390px 화면](../artifacts/review_ui_finish/04-narrow-screen.png) | **저장 결과 재생**이며 새 응답·새 정확도 검증·사용자 직접 확인이 아니다. 최신 app.py/display.py/테마와 전체 원래 인용 표시를 확인한 범위다. [앞선 표시 단계](../artifacts/review_display/implementation_report.md)는 과거 증거로 보존. |
| 과거 전환·복원 화면 | [업그레이드 당시 A 복원](../artifacts/review_upgrade/browser/03-restored.png), [당시 브라우저 결과](../artifacts/review_upgrade/browser/browser_results.json) | Codex가 당시 같은 탭 A→B→A를 확인했다. 사용자 직접 확인은 [UA-07](USER_ACCEPTANCE.md)에서 별도로 미실시 상태다. |
| 셀프/상호 점검·제출 전 확인 | [공식 양식 작성 안내·사본](CHECKLIST_GUIDE.md), [사용자 직접 점검표](USER_ACCEPTANCE.md), [과거 증거 기반 점검표](PRESENTATION.md#자기점검과-동료점검) | 지정 양식 수령 확인·사본 준비. 현재 사용자/동료 직접 점검과 실제 결과 이관은 **미실시**. 기존 Codex 결과를 본인·동료의 결과로 옮기지 않는다. |

`docs/PRESENTATION.md`의 기존 원고는 제출 필수 산출물이 아니다. 파일명은 유지하되 향후 사용하는 부분은 미확인 브라우저 절차와 자기/동료 점검표이며, 원고는 기준본의 역사 자료로만 남긴다.

### 기존 화면 3장의 의미

1. [01-interstellar.png](../artifacts/review_browser_demo/01-interstellar.png): 실제 질문·실제 응답, 놀란/169분과 동일 출처 복수 구절.
2. [02-moon-verification.png](../artifacts/review_browser_demo/02-moon-verification.png): **보완 전** 실제 질문에서 감독이 근거 부족으로 남은 실패. 이후 CLI 성공으로 이 화면의 결과를 바꾸지 않는다.
3. [03-status-replay.png](../artifacts/review_browser_demo/03-status-replay.png): 안내 표시 확인용 **저장 결과 재생·API 없음**. 실제 호출·수정 후 모델 성공 증거가 아니다.

이전 기준본 문서 정리 당시에는 새 화면을 촬영하지 않았다. 최신 실제 호출 화면과 이후 저장 결과 재생 화면은 위 표에서 구분했다. 이번 준비에서는 질문·자동 시연·새 화면 촬영을 하지 않았다. 사용자가 직접 확보한 화면만 사용자 증거로 추가하며 모든 항목을 과거 화면만으로 증명했다고 주장하지 않는다.

## 데이터·이용 조건과 포함 정책

원문에서 **원본 데이터·배포 ZIP·Chroma 전체를 제출 ZIP에 반드시 포함하라는 지시는 확인되지 않았다.** 데이터 수집/색인 스크립트 포함과 원본 데이터 포함은 다른 요구다. 추가 강사 지침은 미확인이다.

| 자료 | 최종 제출 ZIP 준비안 | 수업 제출 때의 판단 |
|---|---|---|
| 코드·프롬프트·설정 예시·문서·선별한 검증 증거 | 포함 | 제출의 중심 파일. 예시 설정에는 키 값을 넣지 않는다. |
| `movies.json`·전체 스냅샷 ZIP | 제외 | [기존 이용 조건 기록](../artifacts/review_director_field/source_conditions.md)상 TMDB 메타데이터의 별도 재배포 허락은 미확인이다. 기본 제출안은 준비 절차와 출처만 포함하고, 별도 포함 요구와 권한이 확인될 때만 허용 범위로 별도 제공한다. |
| Chroma·성공 캐시·브라우저 프로필 | 제외 | 불필요한 실행 저장소다. 재현은 데이터 준비·증분 색인 절차로 안내한다. 별도 전달 요청이 있으면 범위·권한부터 확인한다. |
| `.env`·키·가상환경·Python 캐시 | 제외 | 수업 제출물에도 포함하지 않는다. |
| 위키백과 유래 짧은 발췌·출처 화면 | 선별 증거에 포함 | 기여자/원문 URL·CC BY-SA 4.0·추출/청킹/발췌 표시를 기존 이용 조건 기록과 함께 보존한다. 개별 문서 예외 전체를 확인한 것은 아니다. 전체 데이터 제외만으로 발췌 표시 의무가 사라지지 않는다. |

KOBIS 공식 약관은 [이전 마무리](../artifacts/review_completion/kobis/verification.md)에서 확인했다. TTL 재사용 허용 근거가 없어 기본값은 **0초**다. 새 명시 조회와 현재 화면의 일반 rerun 재표시를 구분하고 실제 수치 표·응답을 파일·DB·LLM·제출 증거로 복제하지 않는다. 현재 화면의 임시 표시까지 포괄 허가받았다고 단정하지 않는다. 기존 TMDB/위키 조건 전체를 새로 확인한 것도 아니므로 **NF2007 전체 준수·공개 재배포 가능은 계속 미확인**이다.

## 검토 ZIP과 향후 수업 제출 ZIP

기존 `artifacts/movie_lab_submission_baseline_review.zip`과 `artifacts/movie_lab_upgrade_review.zip` 및 이전 검토 ZIP은 덮어쓰지 않는다. 기존 ZIP의 이름만 바꿔 최신 제출물로 쓰지 않는다. **사용자 직접 결과를 반영한 뒤 현재 폴더의 최신 파일로 새 제출 ZIP을 구성한다.** 최신 display.py, 역할 실행기, 직접 점검표, 관련 증거를 명시적으로 포함하고 압축 무결성·파일별 SHA-256·문서 상대 링크·제외 항목을 검사한다. 아직 사용자 결과가 없으므로 지금 최종 제출 ZIP을 만들지 않는다.

수업 제출은 아래 구성으로 준비한다. 실제 이름의 미확정 자리에는 개인 정보나 마감을 만들어 넣지 않는다. 최종 압축 파일을 준비해도 외부 업로드·실제 제출은 별도이며 수행하지 않는다.

```text
AI코어프로젝트2_[주제명]_지역_반_성명.zip  # 정보 확인 후 이름 확정
  README.md                              # 목적·실행·설계·데이터 준비
  docs/REQUIREMENTS.md                    # 요구 정의·통합 결과/증거 연결
  docs/USER_ACCEPTANCE.md                 # 사용자의 실제 직접 점검 결과/증거
  docs/CHECKLIST_GUIDE.md                 # 수령한 공식 양식·작성 안내·참고 증거
  docs/PRESENTATION.md                    # 자기/상호·브라우저 점검; 기존 원고는 선택 보존
  docs/SUBMISSION.md                      # 구성·누락·조건
  docs/STREAMLIT_LAB.md                   # 기존 실습 안내 보존
  app.py, movie_lab/, prompts/, scripts/, tests/
  scripts/run_review_profile.ps1          # 생성4o-mini·검토5.4-mini
  step0~step8 Python 파일, plus_widget_key.py
  requirements.txt, requirements-project.txt, AGENTS.md
  .gitignore, .env.example, .streamlit/config.toml, .vscode/settings.json
  artifacts/                             # 연결된 증거만; 원본 데이터/저장소 제외
  submission/checklists/                  # 공식 사본 준비됨; 실제 점검 결과는 아직 없음
```

`artifacts/`는 기본 Git 무시 경로다. 로컬 ZIP에는 선별 증거를 포함하지만 Git README 방식으로 제출한다면 링크한 증거도 허용된 제출 위치에서 열리는지 확인해야 한다. 이번에 무시 규칙 변경·Git 추가·push는 하지 않았다. 과거 검증 스크립트는 검토용 보조 자료이며 일부는 당시 아티팩트를 전제로 하므로 모든 스크립트를 초기 설치에 필요한 실행 단계로 취급하지 않는다.

## 사용자가 마지막으로 확인할 항목

- [ ] PDF의 이름 형식·제출처 외에 실제 지역·반·성명·개인 주제명·구체 마감과 추가 강사 지침 확인. 자리표시자를 확정 정보로 쓰지 않기.
- [x] 수업 제공 셀프/상호 양식 수령 확인 및 XLSX 작성준비본 생성. 실제 점검 완료를 뜻하지 않음.
- [ ] 실제 셀프/상호 결과·점검자·일시·증빙을 공식 양식에 반영하기.
- [ ] 동료와 실제 상호 점검 후 점검자·시각·문제·결과·증거 기록. 미실시를 임의 완료로 바꾸지 않기.
- [x] 과거 혼합 질문·동일 탭 A→B→A의 Codex 실제 Chrome 증거는 보존. 사용자/동료의 별도 직접 점검을 대신하지 않음.
- [ ] [USER_ACCEPTANCE.md](USER_ACCEPTANCE.md)의 직접 절차를 실시하고 실제 결과·증거·확인자·시각 전달. 현재 모든 행 미실시.
- [ ] KOBIS는 키가 준비된 경우에만 선택 점검. 정상 날짜 명시 조회1회와 일반 rerun을 구분하고, 실제 수치 표를 증거로 복제하지 않기. 키가 없으면 선택 기능·실제 연결 미확인 유지.
- [ ] 새 환경의 데이터/스냅샷 경로·키 준비, 실제로 제출할 파일에서 문서와 증거가 열리는지 확인. 이번에 깨끗한 PC 재설치 시연은 하지 않음.
- [ ] 데이터 포함이 추가로 요구되면 재배포 권한과 문서별 표시 조건부터 확인.
- [ ] 요구된 검증 화면의 부족분과 선택 기능 미판정을 확인하고 제출 전 점검 결과 기록.

실시하지 않은 점검·제출을 이 문서의 체크리스트 작성만으로 완료 처리하지 않는다.
