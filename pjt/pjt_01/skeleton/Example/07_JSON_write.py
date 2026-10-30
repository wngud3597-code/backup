"""
07_JSON_write.py
주제: 파이썬 객체를 JSON 으로 저장 (json.dumps / json.dump)
None / _____ 로 표시된 부분을 채워봅니다.
"""

import json
from pathlib import Path


# 저장할 폴더가 없으면 에러 -> 먼저 폴더 보장
Path('sample_data').mkdir(exist_ok=True)

data = {
    'name': '파일 저장하기',
    'value': 20,
}

# [힌트] dict 를 JSON '문자열'로 바꾸는 json 메서드는? (s = string)
json_string = json.dumps(data, ensure_ascii=False, indent=4)  # TODO
new_json_1 = Path('sample_data/sample1.json')
# [힌트] 문자열을 파일에 통째로 저장하는 메서드는?
new_json_1.write_text(json_string, encoding='utf-8')  # TODO

new_json_2 = Path('sample_data/sample2.json')
with new_json_2.open('w', encoding='utf-8') as f:
    # [힌트] dict 를 파일에 '바로' 저장하는 json 메서드는?
    json.dump(data, f, ensure_ascii=False, indent=4)  # TODO

print('저장 완료 :', new_json_1, '/', new_json_2)
