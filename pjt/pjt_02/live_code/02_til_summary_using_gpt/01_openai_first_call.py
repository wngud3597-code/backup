'''
01_openai_first_call.py
    - SSAFY GMS 를 통한 OpenAI Responses API '첫 호출' 확인

🎯 학습 목표
    1) base_url 만 바꾸면 GMS 프록시를 태울 수 있다는 것을 확인한다.
    2) Responses API 의 3요소(model / instructions / input)를 눈으로 익힌다.
    3) 응답에서 output_text / status / usage 를 꺼내 본다.

📝 결과물
    본 실습(02번)에 들어가기 전에 '내 키가 살아 있는지'를 먼저 확인한다.
    파일 요약·저장은 02번에서 제대로 다룬다.

📌 준비
    1) .env.example 을 복사해 .env 로 만들고 GMS_KEY 를 입력
    2) pip install openai python-dotenv

📌 Responses API 3요소 = 아르바이트생에게 일 시키기
    model        : 어떤 직원을 부를지            -> 'gpt-5-nano'
    instructions : 직무 설명서 (= 페르소나)      -> 예전 messages 의 'system'
    input        : 오늘의 업무 지시              -> 예전 messages 의 'user'
    output_text  : 직원이 정리해 돌려준 결과물

[데이터 흐름]
    내 코드 --(요청)--> GMS(LLM Gateway) --(중계)--> OpenAI
    내 코드 <--(응답)-- GMS              <--(결과)-- OpenAI
'''

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# ---------------------------------------------------------------------------
# 1. 설정 (Configuration) - 여기는 그대로 두고 읽기만 하세요
# ---------------------------------------------------------------------------
# load_dotenv() 는 '실행 위치'에서 .env 를 찾습니다.
# 파일 기준 절대 경로를 넘겨야 어디서 실행하든 같은 .env 를 읽습니다.
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')

GMS_KEY = os.getenv('GMS_KEY')
# OpenAI 공식 서버(api.openai.com) 대신 이 주소로 보내면 GMS 가 대신 중계한다.
GMS_BASE_URL = 'https://gms.ssafy.io/gmsapi/api.openai.com/v1'
MODEL = 'gpt-5-nano'

if not GMS_KEY:
    raise SystemExit('GMS_KEY 를 찾을 수 없습니다. .env 파일을 확인하세요.')


# ---------------------------------------------------------------------------
# 2. 클라이언트 생성
# ---------------------------------------------------------------------------
# [실습 포인트] OpenAI 객체를 만들 때 api_key 와 base_url 두 가지를 넘깁니다.
#   base_url 을 빼먹으면 SSAFY 키로 OpenAI 본사에 요청하게 되어 인증 실패(401)합니다.
# TODO: OpenAI 클라이언트를 생성해 client 에 담으세요.
#   힌트: OpenAI(api_key=..., base_url=...)
client = OpenAI(api_key=GMS_KEY, base_url=GMS_BASE_URL)


# ---------------------------------------------------------------------------
# 3. 첫 호출 (Responses API)
# ---------------------------------------------------------------------------
print('🤖 gpt-5-nano 에게 첫 요청을 보냅니다...')

# [실습 포인트] 3요소를 채워 호출합니다. instructions 는 '역할', input 은 '지시'입니다.
#   힌트: client.responses.create(model=..., instructions=..., input=...)
# TODO: 요청을 보내고 결과를 response 에 담으세요.
#   instructions 예) '너는 한국어로 간결하게 답하는 조수야.'
#   input        예) '파이썬에서 API 를 호출한다는 게 무슨 뜻인지 두 문장으로 설명해줘.'
response = client.responses.create(
    model=MODEL,  # 어떤 모델을 부를지 (필수)
    instructions='너는 한국어로 간결하게 답하는 조수야.',  # 역할·규칙 = 페르소나
    input='파이썬에서 API 를 호출한다는 게 무슨 뜻인지 두 문장으로 설명해줘.',  # 업무 지시 (필수)
)


# ---------------------------------------------------------------------------
# 4. 결과 / 상태 / 사용량 확인 - 여기는 그대로 두세요
# ---------------------------------------------------------------------------
# output_text : 여러 조각으로 나뉜 출력을 하나로 합쳐주는 편의 속성
# status      : 'completed' 정상 / 'incomplete' 출력 한도에 걸려 잘림
# usage       : 입력·출력·합계 토큰. 사용량이 곧 비용입니다.
print('\n--- 응답 ---')
print(response.output_text)

print('\n응답 상태 :', response.status)
if response.usage:
    print(
        '토큰 사용량 : '
        f'입력 {response.usage.input_tokens} / '
        f'출력 {response.usage.output_tokens} / '
        f'합계 {response.usage.total_tokens}'
    )

print('\n✅ 연결 확인 완료. 이제 02번 파일로 넘어갑니다.')


# ---------------------------------------------------------------------------
# 🚀 도전 과제 (시간이 남으면)
#   1) instructions 를 '너는 초등학생에게 설명하는 선생님이야' 로 바꿔보고
#      같은 input 에 답이 어떻게 달라지는지 비교해 보세요.
#   2) 같은 코드를 두 번 실행해 보고, 결과가 매번 조금씩 다른 이유를 생각해 보세요.
# ---------------------------------------------------------------------------
