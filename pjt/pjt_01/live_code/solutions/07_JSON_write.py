"""
07_JSON_write.py
주제: 파이썬 객체를 JSON 으로 저장 (json.dumps / json.dump)

핵심 개념
  - dumps() : 파이썬 객체 -> JSON '문자열' 로 변환  (s = string)
  - dump()  : 파이썬 객체 -> JSON '파일' 로 바로 저장
  - ensure_ascii=False : 한글 등 비ASCII 문자를 (\\uXXXX 가 아닌) 원문 그대로 저장
  - indent=4           : 사람이 보기 좋게 4칸 들여쓰기
"""

import json
from pathlib import Path


# 저장할 폴더가 없으면 write/dump 시 에러 -> 먼저 폴더 보장
Path('sample_data').mkdir(exist_ok=True)

data = {
    'name': '파일 저장하기',
    'value': 20,
}

# 1) dumps : dict -> JSON 문자열 로 바꾼 뒤 write_text 로 저장
json_string = json.dumps(data, ensure_ascii=False, indent=4)
new_json_1 = Path('sample_data/sample1.json')
new_json_1.write_text(json_string, encoding='utf-8')

# 2) dump : dict 를 파일에 '바로' 저장 (문자열 변환 단계 생략)
new_json_2 = Path('sample_data/sample2.json')
with new_json_2.open('w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=4)

print('저장 완료 :', new_json_1, '/', new_json_2)
