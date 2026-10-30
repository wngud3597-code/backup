'''
02_aladin_api.py - 인증 키가 필요한 API 호출 (알라딘 상품 검색 API)

🎯 학습 목표
    1) API 키를 소스 코드가 아닌 .env 파일로 분리한다.
    2) params 딕셔너리로 쿼리 스트링을 안전하게 조립한다.
    3) 중첩된 JSON 응답에서 원하는 목록을 반복문으로 가공한다.

📝 결과물
    알라딘 API 로 제목을 검색해 도서 목록을 보기 좋게 출력한다.

📌 준비
    1) 알라딘 TTB Key 발급: https://www.aladin.co.kr/ttb/wblog_manage.aspx
    2) .env.example 을 복사해 .env 로 만들고 키를 입력
       Windows: copy .env.example .env  /  macOS: cp .env.example .env

📌 비유 - API 키 = 도서관 회원증
    누구나 들어갈 수 있는 열람실(Dog API)과 달리,
    회원증을 보여줘야만 열리는 서고(알라딘 API)가 있습니다.
    회원증 번호를 벽에 붙여두면(= 코드에 하드코딩) 아무나 쓰게 되므로
    지갑(.env)에 넣어 다닙니다.

📌 응답 구조
    { 'totalResults': 123, 'item': [ {'title': ..., 'author': ...}, ... ] }

⚠️ .env 파일은 절대 Git/공유 드라이브에 올리지 않습니다.
   대신 .env.example 로 '어떤 키가 필요한지'만 공유합니다.

📌 실습 TODO : 5개
'''

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# 1. 환경 변수 로드
# ---------------------------------------------------------------------------
# load_dotenv() 는 기본적으로 '실행 위치'에서 .env 를 찾습니다.
# 다른 폴더에서 실행해도 안전하도록 파일 기준 절대 경로를 만들어 씁니다.
# (Path(__file__).resolve().parent = '이 파일이 있는 폴더')
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')

# [실습 포인트] 환경 변수 읽기
#   힌트: os.getenv('키_이름')  /  .env 에 적은 키 이름은 TTBKEY 입니다.
# TODO 1: .env 에 저장한 TTBKEY 값을 읽어오세요.
TTB_KEY = os.getenv('TTBKEY')

# 키를 못 읽어오는 상황을 조기에 잡아줍니다.
if not TTB_KEY:
    raise SystemExit(
        'TTBKEY 를 찾을 수 없습니다. .env 파일과 키 이름을 확인하세요.'
    )


# ---------------------------------------------------------------------------
# 2. 요청 정보 구성
# ---------------------------------------------------------------------------
URL = 'https://www.aladin.co.kr/ttb/api/ItemSearch.aspx'

# [실습 포인트] 쿼리 스트링(? 뒤에 &로 이어지는 부분)은
#   문자열로 직접 이어 붙이지 말고 딕셔너리로 넘깁니다.
#   requests 가 한글·공백 인코딩까지 알아서 처리해 줍니다.
# TODO 2: 아래 params 의 ttbkey 와 Query 를 채우세요.
params = {
    'ttbkey': TTB_KEY,  # 발급받은 키 (위에서 읽어온 변수)
    'Query': '오디세이',  # 검색어
    'QueryType': 'Title',  # Title / Author / Publisher
    'MaxResults': 10,
    'start': 1,
    'SearchTarget': 'Book',
    'output': 'js',  # js = JSON 형식으로 응답
    'Version': '20131101',
}


# ---------------------------------------------------------------------------
# 3. 요청 전송 및 응답 확인
# ---------------------------------------------------------------------------
# [실습 포인트] params 인자를 넘기면 requests 가 URL 을 대신 조립해 줍니다.
# TODO 3: GET 요청을 보내고 response 에 담으세요.
#   힌트: requests.get(URL, params=params, timeout=5)
response = requests.get(URL, params=params, timeout=5)

# params 가 어떻게 URL 로 바뀌었는지 눈으로 확인하는 것이 목적입니다.
print('상태 코드   :', response.status_code)
print('요청한 주소 :', response.url)

data = response.json()


# ---------------------------------------------------------------------------
# 4. 응답 가공
# ---------------------------------------------------------------------------
# 없을 수도 있는 키는 .get(키, 기본값) 으로 안전하게 꺼냅니다.
print('\n총 검색 결과 :', data.get('totalResults'), '건')

# [실습 포인트] 'item' 키가 아예 없을 수도 있습니다.
#   기본값을 빈 리스트로 주면 아래 반복문이 에러 없이 그냥 넘어갑니다.
# TODO 4: 도서 목록(item)을 items 에 담으세요. 없으면 빈 리스트가 되게 하세요.
items = data.get('item')

print(f'가져온 도서   : {len(items)} 권\n')
print('-' * 60)

# [실습 포인트] enumerate(리스트, start=1) 를 쓰면 번호를 함께 얻을 수 있습니다.
#   각 book 은 딕셔너리입니다. 어떤 키가 있는지 모르겠다면
#   pprint(items[0]) 으로 첫 번째 항목만 먼저 찍어보세요.
# TODO 5: 반복문으로 번호 / 제목(title) / 저자(author) / 출간일(pubDate)을 출력하세요.
#   힌트: for idx, book in enumerate(items, start=1):
for idx, book in enumerate(items, start=1):
    title = book.get('title')
    author = book.get('author')
    pub_date = book.get('pubDate')
    price = book.get('priceSales')

    print(f'{idx:2d}. {title}')
    print(f'    저자   : {author}')
    print(f'    출간일 : {pub_date} / 판매가 : {price:,}원')
    print('-' * 60)


# ---------------------------------------------------------------------------
# 🚀 도전 과제
#   1) QueryType 을 'Author' 로 바꿔 저자로 검색해 보세요.
#   2) 검색어를 input() 으로 받아 사용자가 직접 입력하게 만들어 보세요.
#   3) 검색 결과를 JSON 파일(books.json)로 저장해 보세요.
#      힌트: import json / json.dump(data, f, ensure_ascii=False, indent=2)
# ---------------------------------------------------------------------------
