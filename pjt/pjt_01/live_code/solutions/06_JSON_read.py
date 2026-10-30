"""
06_JSON_read.py
주제: JSON 파일 읽고 파이썬 객체로 변환 (json.loads / json.load)

사전 준비 : 'sample_data/' 폴더에 'books_20.json' 이 있어야 함

핵심 개념
  - JSON 은 '문자열' 형식 -> 파이썬에서 쓰려면 dict/list 로 '변환'이 필요
  - loads() : 문자열(string)  을 파이썬 객체로 변환  (s = string)
  - load()  : 파일(file 객체) 을 파이썬 객체로 변환
"""

import json
from pathlib import Path


json_file = Path('sample_data/books_20.json')

# 1) loads : 먼저 파일을 '문자열'로 읽은 뒤 -> dict 로 변환
json_text = json_file.read_text(encoding='utf-8')
print(type(json_text))  # <class 'str'>  (아직 문자열!)

data = json.loads(json_text)
print(type(data))       # <class 'dict'>  (변환 완료)


# 2) load : 파일을 열어 '파일 객체'를 그대로 변환 (문자열 단계 생략)
#    [주의] 경로 객체(json_file)와 파일 핸들은 이름을 분리 -> 여기선 as f
with json_file.open(encoding='utf-8') as f:
    data = json.load(f)
    print(type(data))   # <class 'dict'>
