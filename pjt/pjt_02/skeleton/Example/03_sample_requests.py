import requests

# 간단한 요청 예제
URL = 'https://dog.ceo/api/breeds/image/random'

response = requests.get(URL).json() # JSON 응답을 Dictionary로 변환환
print(response)

results = response.get('message')   # 응답 결과에서 필요한 부분 가져오기기
print(results)


# 필요한 모듈 임포트
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 환경 변수 접근
TTBKEY = os.getenv('TTBKEY')
# 알라딘 API 요청 예제
URL = 'https://aladin.co.kr/ttb/api/ItemSearch.aspx'
# 필요한 파라미터 전달을 위한 Dictionary
params = {
    'ttbkey': TTBKEY,           # 부여받은 TTBKey
    'Query': '파울로 코엘료',
    'QueryType': 'Author',
    'MaxResults' : 20,
    'start' : 1,
    'SearchTarget' : 'Book',
    'output' : 'js',
    'Version' : '20131101'
}
response = requests.get(URL, params=params) # 요청시 위에서 설정한 파라미터 정보를 같이 전달
response = response.json()
