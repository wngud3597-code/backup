'''
02_TIL_summary_with_openai_function.py
    - 이번 실습의 본체. TIL 폴더 전체를 함수 단위로 요약한다.

선행 : 01_openai_first_call.py 로 GMS 연결이 확인된 상태에서 시작합니다.

🎯 학습 목표
    1) 하나의 스크립트를 역할별 함수로 분리한다. (단일 책임 원칙)
    2) pathlib 로 폴더 안의 여러 마크다운 파일을 순회한다.
    3) input 에 문자열 대신 '메시지 리스트'를 넘기는 방식을 익힌다.
    4) 자동 저장 전에 사람이 확인하는 절차(Human-in-the-loop)를 넣는다.

📝 결과물
    TIL 폴더의 모든 .md 파일을 합쳐 한 번에 요약하고,
    사람이 확인한 뒤에 summary.md 로 저장한다.

📌 왜 함수로 쪼개나?
    단발 호출(01번) = 라면 한 번 끓이기 (순서대로 쭉)
    02번            = 라면 가게 주방 만들기 (재료 준비 / 조리 / 담기 공정 분리)
    => 모델을 바꾸고 싶으면 request_summary() 한 곳만 고치면 됩니다.

[데이터 흐름]
    find_md_files()        TIL 폴더에서 .md 목록 수집          [TODO 1]
        ↓
    merge_md_files()       파일명을 붙여 하나의 문자열로 병합    [TODO 3]
        ↓ (내부에서 read_file() 호출)                        [TODO 2]
    build_messages()       [system 페르소나] + [user 원문]     [TODO 4]
        ↓
    request_summary()      client.responses.create() 호출      [TODO 5]
        ↓
    confirm_before_save()  🧑 사람이 결과를 확인 (HITL)         [TODO 6]
        ↓
    save_response()        AI 생성 고지를 붙여 저장             [TODO 7]
        ↓
    summary_using_gpt()    위 함수들을 순서대로 조립            [TODO 8]

📌 실습 TODO : 8개 — 위에서부터 하나씩 채우고, 중간중간 실행해 보세요.
'''

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# ---------------------------------------------------------------------------
# 설정 (Configuration) - 01번에서 이미 해봤으므로 완성해 두었습니다
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')

GMS_KEY = os.getenv('GMS_KEY')
GMS_BASE_URL = 'https://gms.ssafy.io/gmsapi/api.openai.com/v1'
MODEL = 'gpt-5-nano'

# True 로 두면 저장 직전에 사람이 확인합니다. (Human-in-the-loop)
CONFIRM_BEFORE_SAVE = True

PERSONA = '''
당신은 프로그래밍 비전공 입문자가 작성한 마크다운 학습 노트를 요약하는 전문가입니다.

작성 규칙
- 문서 전체를 관통하는 핵심 키워드를 먼저 5개 내외로 뽑아 제시합니다.
- 여러 노트의 내용을 주제별로 묶어 재구성합니다.
- 어려운 용어는 비전공자가 이해할 수 있는 쉬운 표현으로 풀어 씁니다.
- 최종 출력은 가독성 좋은 마크다운 형식으로 작성합니다.
'''


# ---------------------------------------------------------------------------
# 1. 파일 입출력 담당 함수
# ---------------------------------------------------------------------------
def find_md_files(folder_path):
    '''지정한 폴더에서 .md 파일 목록을 정렬해서 반환한다.'''
    folder = Path(folder_path)

    if not folder.is_dir():  # 폴더가 없으면 빈 리스트로 반환
        print(f'⚠️ 폴더가 없습니다: {folder}')
        return []

    # [실습 포인트] glob() 은 파일을 찾아줄 뿐 순서까지 정해주지 않습니다.
    #   sorted() 로 감싸는 한 줄이 '재현성'(같은 입력이면 같은 결과)을 만듭니다.
    #   학습 노트는 1일차 -> 5일차 순서로 읽혀야 의미가 있으니까요.
    # TODO 1: .md 파일 목록을 정렬해서 반환하세요.
    #   힌트: sorted(folder.glob('*.md'))
    return sorted(folder.glob('*.md'))


def read_file(target_file):
    '''파일 하나를 읽어 문자열로 반환한다. 실패하면 None.'''
    file_path = Path(target_file)

    # 파일이 없어도 여기서 멈추지 않아야 나머지 파일을 계속 읽을 수 있습니다.
    if not file_path.exists():
        print(f'⚠️ 파일이 존재하지 않습니다: {file_path}')
        return None

    # [실습 포인트] encoding='utf-8' 을 빼면 한글이 깨질 수 있습니다.
    # TODO 2: 파일을 열어 내용 전체를 읽어 반환하세요.
    #   힌트: with file_path.open('r', encoding='utf-8') as f:
    with file_path.open('r', encoding='utf-8') as f:
        return f.read()


def merge_md_files(folder_path):
    '''폴더 안의 모든 .md 내용을 하나의 문자열로 병합한다.'''
    md_files = find_md_files(folder_path)

    chunks = []
    for md_file in md_files:
        data = read_file(md_file)
        if data is None:
            continue

        # [실습 포인트] 그냥 이어 붙이면 모델은 하나의 긴 글로 인식합니다.
        #   파일명을 제목처럼 붙여주면 문서의 '경계'가 생겨 요약 품질이 좋아집니다.
        # TODO 3: f'## [파일: {md_file.name}]\n{data}' 형태로 chunks 에 추가하세요.
        chunks.append(f'## [파일: {md_file.name}]\n{data}')

    print(f'📄 병합한 파일 : {len(chunks)}개')

    # 리스트가 아니라 하나의 문자열로 반환해야 그대로 요청에 담을 수 있습니다.
    return '\n\n---\n\n'.join(chunks)


# ---------------------------------------------------------------------------
# 2. LLM 호출 담당 함수
# ---------------------------------------------------------------------------
def get_client():
    '''GMS 프록시를 사용하는 OpenAI 클라이언트를 생성한다. (01번과 동일)'''
    if not GMS_KEY:
        raise SystemExit(
            'GMS_KEY 를 찾을 수 없습니다. .env 파일을 확인하세요.'
        )

    return OpenAI(api_key=GMS_KEY, base_url=GMS_BASE_URL)


# 대화 메시지 만들기
def build_messages(persona, user_content):
    '''Responses API 에 넘길 메시지 리스트를 만든다.

    [실습 포인트] Responses API 의 input 은 두 가지 형태를 모두 받습니다.
      (1) 문자열       : input='요약해줘'                     <- 01번에서 쓴 방식
      (2) 메시지 리스트 : input=[{'role': 'system', ...}, ...] <- 이번에 쓸 방식
    여러 역할을 섞거나 대화를 누적하려면 (2)를 씁니다.
    '''
    # TODO 4: system(페르소나) + user(원문) 두 개짜리 리스트를 반환하세요.
    #   힌트: [{'role': 'system', 'content': persona}, {'role': 'user', ...}]
    return [
        {'role': 'system', 'content': persona}, 
        {'role': 'user', 'content': user_content},
    ]


# 요약 요청
def request_summary(client, messages):
    '''gpt-5-nano 에 요약을 요청하고 결과 텍스트를 반환한다.'''
    # TODO 5: 요약을 요청하고 결과를 response 에 담으세요.
    #   힌트: client.responses.create(
    #             model=MODEL,
    #             input=messages,
    #             reasoning={'effort': 'medium'},  # 추론 강도
    #         )
    response = client.responses.create(
        model=MODEL,  # 사용할 모델 (필수)
        input=messages,  # 대화 메시지 목록 (필수)
        # gpt-5 계열 전용 옵션. 필요할 때 주석을 해제해 실험해 본다.
        reasoning={
            'effort': 'medium'
        },  # 추론 강도: minimal / low / medium / high
        # text={'verbosity': 'medium'},    # 답변 길이: low / medium / high
        # max_output_tokens=4000,          # 출력 토큰 상한
    )

    # [디버깅 포인트] 응답이 잘렸는지, 토큰을 얼마나 썼는지 확인하는 습관 (여기는 완성되어 있습니다)
    print('응답 상태 :', response.status)
    if response.status == 'incomplete':
        print('⚠️ 답변이 중간에 잘렸습니다. max_output_tokens 를 늘려보세요.')
    if response.usage:
        print(
            '토큰 사용량 : '
            f'입력 {response.usage.input_tokens} / '
            f'출력 {response.usage.output_tokens} / '
            f'합계 {response.usage.total_tokens}'
        )

    return response.output_text


# ---------------------------------------------------------------------------
# 3. 사람 검토 지점 (Human-in-the-loop)
# ---------------------------------------------------------------------------
def confirm_before_save(summary_text):
    '''결과를 미리 보여주고 저장 여부를 사람에게 묻는다.

    [실습 포인트] AI 결과를 곧바로 파일에 덮어쓰면 잘못된 요약이 조용히
    원본을 대체할 수 있습니다. 자동문에도 사람이 누르는 '열림 버튼'이 있듯,
    자동화 흐름에 사람이 승인하는 한 칸을 두는 것이 에이전트 설계의 기본 원칙입니다.
    '''
    print('\n' + '=' * 60)
    print(summary_text[:500])
    print('=' * 60)
    print('(위는 앞부분 500자 미리보기입니다)')

    # TODO 6: input() 으로 저장 여부를 묻고, 'y' 일 때만 True 를 반환하세요.
    #   힌트: input('\n이 내용을 저장할까요? [y/N] ').strip().lower()
    answer = input('\n이 내용을 저장할까요? [y/N] ').strip().lower()
    return answer == 'y'


# ---------------------------------------------------------------------------
# 4. 저장 담당 함수
# ---------------------------------------------------------------------------
def save_response(response_text, file_name='summary.md'):
    '''요약 결과에 AI 생성 고지를 붙여 마크다운 파일로 저장한다.'''
    file_path = BASE_DIR / file_name

    # [실습 포인트] AI 가 만든 문서에는 '누가 만들었는지'를 밝혀야 합니다.
    #   사람이 매번 기억해서 적는 대신, 코드가 책임지게 만드는 자리입니다.
    disclosure = (
        f'\n\n---\n'
        f'> 🤖 이 문서는 AI(`{MODEL}`)가 자동 생성한 요약본입니다. '
        f'내용의 정확성은 반드시 사람이 검토해 주세요.\n'
    )

    # TODO 7: response_text + disclosure 를 file_path 에 저장하세요.
    #   힌트: with file_path.open('w', encoding='utf-8') as f:
    with file_path.open('w', encoding='utf-8') as f:
        f.write(response_text + disclosure)

    print(f'✅ 저장 완료 : {file_path.name}')


# ---------------------------------------------------------------------------
# 5. 전체 흐름 조립
# ---------------------------------------------------------------------------
def summary_using_gpt(persona, folder_path):
    '''TIL 폴더를 요약해 summary.md 로 저장하는 전체 파이프라인.'''
    # TODO 8: 위에서 만든 함수들을 순서대로 호출해 파이프라인을 완성하세요.
    #   1) merge_md_files(folder_path) 로 원문 병합 -> 비어 있으면 안내 후 return
    #   2) get_client() 로 클라이언트 생성
    #   3) build_messages(persona, 원문) 으로 메시지 구성
    #   4) request_summary(client, messages) 로 요약 요청
    #   5) CONFIRM_BEFORE_SAVE 가 True 면 confirm_before_save() 로 확인
    #      (사람이 y 를 누르지 않으면 저장하지 않고 return)
    #   6) save_response() 로 저장
    user_data = merge_md_files(folder_path)

    if not user_data:
        print('⚠️ 요약할 내용이 없습니다. 폴더 경로를 확인하세요.')
        return

    client = get_client()
    messages = build_messages(persona, user_data)

    print('🤖 gpt-5-nano 에게 요약을 요청합니다...')
    summary_text = request_summary(client, messages)

    if CONFIRM_BEFORE_SAVE and not confirm_before_save(summary_text):
        print('⏹️ 저장을 취소했습니다.')
        return

    save_response(summary_text)


if __name__ == '__main__':
    # __name__ == '__main__' 은 '이 파일을 직접 실행했을 때만' 이라는 뜻입니다.
    # 다른 파일에서 import 할 때는 아래 코드가 실행되지 않습니다.
    # (99_module_calling 폴더의 예제를 실행해 직접 확인해 보세요)
    folder_path = BASE_DIR / 'TIL'

    summary_using_gpt(PERSONA, folder_path)


# ---------------------------------------------------------------------------
# 🚀 도전 과제 (수업 후 각자)
#   1) CONFIRM_BEFORE_SAVE 를 False 로 바꿔보고,
#      "사람 확인 없이 자동 저장"이 위험한 상황을 하나 떠올려 보세요.
#   2) TIL 파일이 100개라면 이 코드는 어떤 문제가 생길까요?
#      (힌트: 입력 토큰 한도) 어떻게 해결할 수 있을지 생각해 보세요.
#   3) 요약 결과를 summary.md 대신 'summary_날짜.md' 로 저장해 보세요.
#      힌트: from datetime import datetime
#   4) find_md_files() 의 glob() 을 rglob() 으로 바꾸면 무엇이 달라질까요?
# ---------------------------------------------------------------------------
