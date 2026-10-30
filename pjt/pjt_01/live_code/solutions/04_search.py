"""
04_search.py
주제: 패턴으로 파일/폴더 검색하기 (glob / rglob)

핵심 개념
  - glob(pattern)  : '해당 폴더 바로 아래'에서 패턴에 맞는 항목 검색 (하위 폴더 X)
  - rglob(pattern) : 현재 폴더 + '모든 하위 폴더'까지 재귀적으로 검색 (r = recursive)
  - 패턴의 '*' 는 '아무 문자열'을 의미 -> '*.py' = 확장자가 .py 인 모든 파일
"""

from pathlib import Path

current_path = Path.cwd()

# 1) glob : 현재 폴더에서 .py 파일만 (하위 폴더는 검색 안 함)
for python_file in current_path.glob('*.py'):
    print(python_file.name)

print('=====')

# 2) rglob : 하위 폴더까지 모두 뒤져 .txt 파일 검색
for txt_file in current_path.rglob('*.txt'):
    print(txt_file.name)


# 3) 응용: 이름에 언더스코어(_)가 '정확히 1개'인 파일만 모으기
result = []
for item in current_path.rglob('*_*'):  # 언더스코어를 가진 모든 항목
    # is_file() -> 폴더 제외 / name.count('_') == 1 -> 언더스코어 개수 조건
    if item.is_file() and item.name.count('_') == 1:
        result.append(item.name)

print(result)
