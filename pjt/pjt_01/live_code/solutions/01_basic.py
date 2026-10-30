"""
01_basic.py
주제: pathlib 기초 - 경로 다루기 & 파일 정보 확인

핵심 개념
  - pathlib.Path : 파일 시스템 경로를 '문자열'이 아니라 '객체'로 다루는 표준 라이브러리
  - 왜 pathlib 인가?
      * OS마다 경로 구분자가 다름 (윈도우 '\\' vs 맥/리눅스 '/')
      * pathlib은 이를 자동 처리하고, '/' 연산자로 경로를 직관적으로 결합할 수 있음
      * 구형 os.path 방식보다 코드가 짧고 읽기 쉬움
"""

from pathlib import Path

# =========================================================
# 1. 경로 다루기
# =========================================================

# 현재 작업 디렉토리(Current Working Directory)
# -> 지금 파이썬을 '실행한' 위치. 상대경로의 기준점이므로 항상 먼저 확인하는 습관!
current_path = Path.cwd()
print(f'현재 작업 경로 : {current_path}')

# 홈 디렉토리 (사용자 계정 폴더)
# -> OS마다 실제 경로는 다르지만 코드는 동일하게 동작
home_path = Path.home()
print(f'홈 디렉토리 : {home_path}')

# 특정 경로를 문자열로 직접 지정
# -> 주의: 아직 '실제 파일'이 아니라 '경로를 표현한 객체'일 뿐 (존재 여부와 무관)
specific_path = Path('home/user/documents/file.txt')
print(f'특정 경로 : {specific_path}')

# 경로 결합 : '/' 연산자로 폴더/파일을 이어 붙임 (OS 구분자 자동 처리)
new_path = Path('documents') / 'subfolder' / 'file.txt'
print(f'경로 합치기 : {new_path}')


# =========================================================
# 2. 파일 정보 확인 (경로 객체가 제공하는 속성)
# =========================================================

# .name : 확장자를 '포함'한 파일명 전체  ->  file.txt
file_name = specific_path.name
print(f'파일명(전체) : {file_name}')

# .stem : 확장자를 '제외'한 이름  ->  file
stem = specific_path.stem
print(f'확장자 제외 이름 : {stem}')

# .suffix : 확장자 (점 포함)  ->  .txt
suffix = specific_path.suffix
print(f'파일 확장자 : {suffix}')
