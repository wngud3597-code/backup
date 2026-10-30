# 학습 목표
# - Figma 화면 이미지를 생성형 AI(GMS)에 보내 HTML/CSS 코드로 받아 볼 수 있다.
# - 웹에서 쓰던 프롬프트를 코드로 옮겨, 같은 요청을 반복 실행할 수 있다.
# 실습 TODO : 1개 (+ 주석 해제 1곳)
#
# 실행 전 준비
# - .env.sample 을 복사해 .env 로 이름을 바꾸고 GMS_API_KEY 채우기
# - pip install -r requirements.txt

import os
import base64  # BASE64 인코딩을 위한 라이브러리
from openai import OpenAI
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# .env 파일 로드
load_dotenv()
# 환경 변수 접근
GMS_API_KEY = os.getenv('GMS_API_KEY')
GMS_BASE_URL = os.getenv('GMS_BASE_URL')
MODEL = os.getenv('MODEL')
# GMS API 키 설정
client = OpenAI(api_key=GMS_API_KEY, base_url=GMS_BASE_URL)


# 이미지 인코딩
def encode_image(image_path):
    with Path(image_path).open('rb') as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


# 생성형 AI 에 이미지 + 프롬프트 전송 및 응답
def analyze_image(image_path, prompt):
    base64_image = encode_image(image_path)

    response = client.chat.completions.create(
        model=MODEL,  # gpt-5-nano
        messages=[
            {
                'role': 'system',
                'content': '설명 없이, CSS를 포함한 완성된 HTML 문서 코드만 응답하세요. 코드블럭(```)은 사용하지 마세요.',
            },
            {
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': prompt},
                    {
                        'type': 'image_url',
                        'image_url': {
                            'url': f'data:image/png;base64,{base64_image}'
                        },
                    },
                ],
            },
        ],
    )

    return response.choices[0].message.content


if __name__ == '__main__':
    # 이미지 위치
    target_image_path = BASE_DIR / 'image' / 'login.png'

    # [실습 포인트/힌트]
    # - 교재 'ChatGPT Web service 프롬프팅'에서 사용한 <요구사항>을 그대로 옮겨 오기
    # - Bootstrap 버전, 반응형 기준 화면 폭(412px)처럼 구체적인 숫자를 적을수록 결과가 안정적
    # - 비워 둔 채 실행해도 동작은 함 => 채우기 전과 후의 결과(03_ai_result.html)를 비교해 보기
    # TODO 1: <요구사항> 태그 안의 내용 작성
    prompt = '''
    HTML, CSS, 그리고 Bootstrap을 사용하여 첨부된 이미지와 동일한 디자인의 Navbar와 로그인 입력창을 구현해주세요.

    <요구사항>
    Bootstrap 버전: 반드시 5.3.3을 사용합니다.
    반응형 디자인: 화면 폭 412px에서도 정상적으로 표시되도록 반응형 웹페이지로 구성합니다.
    디자인: 첨부된 이미지를 참고하여 Navbar와 로그인 입력창의 구성 및 스타일이 일치하도록 구현합니다.
    코드 최적화: 필요한 경우 Bootstrap의 컴포넌트와 유틸리티 클래스를 활용하여 코드를 간결하게 작성해주세요.
    이미지: 사용할 이미지가 없으면 텍스트로 대체합니다.
    </요구사항>
    '''

    print(f'이미지 : {target_image_path} 를 HTML/CSS 변환 요청')
    result = analyze_image(target_image_path, prompt)

    # 응답을 파일로 저장
    html = BASE_DIR / '03_ai_result.html'
    with html.open('w', encoding='utf-8') as f:
        f.write(result)

    # [따라하기] 교재 'AI 응답을 파일로 저장할 때'에서 아래 주석을 해제
    # - 위에서 저장한 파일을 정리된 내용으로 다시 덮어씀

    # 응답이 ```html 로 감싸져 온 경우 첫 줄과 마지막 줄 제거
    # result = result.strip()
    # if result.startswith('```'):
    #     result = result.split('\n', 1)[1]
    #     result = result.rsplit('```', 1)[0]

    # AI 생성 초안임을 표시해서 저장
    # html = BASE_DIR / '03_ai_result.html'
    # with html.open('w', encoding='utf-8') as f:
    #     f.write('<!-- AI 생성 초안: 검수 전 -->\n' + result)

    print('코드 변환 완료! 03_ai_result.html 파일 생성')
