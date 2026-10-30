"""
05_read_file.py
주제: 파일 내용 읽어오기 (read_text / read / readline / readlines)
사전 준비 : 02_create.py 를 먼저 실행 (new_directory/new.md 필요)
None / _____ 로 표시된 부분을 채워봅니다.
"""

from pathlib import Path


file_path = Path('new_directory/new.md')

# [힌트] 파일 '전체'를 문자열로 한 번에 반환하는 메서드는?
print(file_path.read_text(encoding='utf-8'))  # TODO


# [힌트] 읽기 모드('r')로 연 뒤, 전체를 반환하는 메서드는?
with file_path.open('r', encoding='utf-8') as file:
    print(file)
    print(file.read())  # TODO: 전체 읽기


# [힌트] '한 줄씩' 반환하는 메서드는? (호출할 때마다 다음 줄)
with file_path.open('r', encoding='utf-8') as file:
    print(file.readline())  # TODO: 첫 줄
    print(file.readline())  # TODO: 다음 줄


# [힌트] 모든 줄을 '리스트'로 반환하는 메서드는?
with file_path.open('r', encoding='utf-8') as file:
    print(file.readlines())  # TODO
