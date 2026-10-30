import os
from dotenv import load_dotenv
from openai import OpenAI

# .env 파일 로드
load_dotenv()

# 환경 변수 접근
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# !! 테스트를 위해서는 API KEY 발급 필요 !!
client = OpenAI(
    base_url='https://gms.ssafy.io/gmsapi/api.openai.com/v1',
    api_key=OPENAI_API_KEY
)

# 페르소나 지정 및 기존 대화 내용 저장
conversation_history = [
    {"role": "system", "content": "당신은 사용자 질문에 답변하는 챗봇입니다."},
    {"role": "system", "content": "답변은 사용자가 읽기 쉽도록 마크다운 형태로 정리해서 출력해줘."},
]

# 질문
conversation_history.append(
    {
        "role": "user",
        "content": "오늘 달달하고 매콤한 것을 먹고 싶은데, 점심 메뉴 추천해줄래?",
    } 
)

# API 호출
response = client.chat.completions.create(
    model="gpt-5-nano",             # 사용하려는 모델 (필수 지정)
    messages=conversation_history,  # 대화 메시지 목록 (필수 지정)
    max_completion_tokens=4080,     # 생성될 응답의 최대 토큰 수 (값의 범위: 1~모델 마다 최대값 ex> gpt-4o-mini: 16,385 tokens)
    temperature=1.0,                  # 확률 분포 조정을 통한 응답의 다양성 제어 (값의 범위: 0~2)
    top_p=1.0,                      # 누적 확률 값을 통한 응답의 다양성 제어 (값의 범위: 0~1)
    n=1,                            # 생성할 응답 수 (1이상의 값)
    seed=1000                       # 랜덤 씨드 값 (설정하는 경우 일관된 답변을 얻을 수 있음)
)

# 응답 출력 (single-turn)
for response in response.choices:
    print(f"Assistant: {response.message.content}")