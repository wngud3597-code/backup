"""
01_basic.py
주제: pathlib 기초 - 경로 다루기 & 파일 정보 확인
수업을 따라가며 TODO 부분을 직접 채워봅니다.
"""

from pathlib import Path


# =========================================================
# 1. 경로 다루기
# =========================================================

# [힌트] '지금 실행 중인 위치'를 반환하는 메서드는? (상대경로의 기준점)
# TODO: 현재 작업 디렉토리를 구해 current_path 에 담기
current_path = Path.cwd()  # TODO
print(f'현재 작업 경로 : {current_path}')

# [힌트] 사용자 홈 폴더를 반환하는 메서드는?
# TODO: 홈 디렉토리를 구해 home_path 에 담기
home_path = Path.home()  # TODO
print(f'홈 디렉토리 : {home_path}')

# 문자열 경로로 Path 객체 만들기 (아직 실제 파일은 아님)
specific_path = Path('home/user/documents/file.txt')
print(f'특정 경로 : {specific_path}')

# [힌트] Path 객체는 '/' 연산자로 경로를 결합할 수 있음
# TODO: 'documents' -> 'subfolder' -> 'file.txt' 순서로 결합해 new_path 에 담기
new_path = Path('documents') / 'subfolder' / 'file.txt'  # TODO
print(f'경로 합치기 : {new_path}')


# =========================================================
# 2. 파일 정보 확인
# =========================================================

# [힌트] 확장자를 '포함'한 파일명 전체를 주는 속성은?
# TODO
file_name = specific_path.name  # TODO
print(f'파일명(전체) : {file_name}')

# [힌트] 확장자를 '제외'한 이름을 주는 속성은?
# TODO
stem = specific_path.stem  # TODO
print(f'확장자 제외 이름 : {stem}')

# [힌트] 확장자(.txt)만 주는 속성은?
# TODO
suffix = specific_path.suffix  # TODO
print(f'파일 확장자 : {suffix}')
