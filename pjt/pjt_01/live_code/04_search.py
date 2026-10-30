"""
04_search.py
주제: 패턴으로 파일/폴더 검색하기 (glob / rglob)
None / _____ 로 표시된 부분을 채워봅니다.
"""

from pathlib import Path


current_path = Path.cwd()

# [힌트] '현재 폴더에서만' 패턴에 맞는 파일을 찾는 메서드는? (하위 폴더 X)
for python_file in current_path.glob('*.py'):  # TODO
    print(python_file.name)

print('=====')

# [힌트] '하위 폴더까지' 재귀적으로 찾는 메서드는? (r = recursive)
for txt_file in current_path.rglob('*.txt'):  # TODO
    print(txt_file.name)


# 응용: 이름에 언더스코어(_)가 '정확히 1개'인 파일만 모으기
result = []
for item in current_path.rglob('*_*'):
    # [힌트] (1) 파일만 걸러내는 메서드  (2) 문자열에서 특정 문자 개수를 세는 메서드
    if item.is_file() and item.name.count('_') == 1:  # TODO
        result.append(item.name)

print(result)
