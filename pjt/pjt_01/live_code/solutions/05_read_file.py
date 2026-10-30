"""
05_read_file.py
주제: 파일 내용 읽어오기 (read_text / read / readline / readlines)

사전 준비 : 02_create.py 를 먼저 실행해 'new_directory/new.md' 가 있어야 함

핵심 개념
  - read_text() : 파일 전체를 문자열로 '한 번에' 반환 (가장 간단)
  - open('r')   : 읽기 모드로 열어 파일 객체(핸들)를 얻음
  - read()      : 파일 전체를 문자열로 반환
  - readline()  : '한 줄'씩 반환 (호출할 때마다 다음 줄로 커서 이동)
  - readlines() : 모든 줄을 '리스트'로 반환 (각 줄 끝의 '\n' 포함)
"""

from pathlib import Path


file_path = Path('new_directory/new.md')

# 1) read_text : 가장 간단하게 전체 내용을 문자열로
print(file_path.read_text(encoding='utf-8'))


# 2) open + read : 파일을 열어 객체를 얻은 뒤 read()
with file_path.open('r', encoding='utf-8') as file:
    print(file)         # 파일 객체 자체 (<_io.TextIOWrapper ...>)
    print(file.read())  # 내용 전체


# 3) readline : 한 줄씩 (커서가 다음 줄로 이동)
with file_path.open('r', encoding='utf-8') as file:
    print(file.readline())  # 첫 번째 줄
    print(file.readline())  # 두 번째 줄


# 4) readlines : 모든 줄을 리스트로 (줄바꿈 '\n' 포함)
with file_path.open('r', encoding='utf-8') as file:
    print(file.readlines())
