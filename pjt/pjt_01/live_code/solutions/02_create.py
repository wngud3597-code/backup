"""
02_create.py
주제: 폴더 & 파일 생성하기 (mkdir / write_text / open 'a')

핵심 개념
  - mkdir(exist_ok=True) : 폴더 생성. 이미 있으면 에러 없이 넘어감
  - write_text()         : 파일에 문자열을 '통째로' 씀 (주의: 기존 내용을 덮어씀)
  - open('a')            : append 모드. 기존 내용 '뒤에 이어서' 씀
  - with 구문            : 파일을 안전하게 열고 자동으로 닫아주는 리소스 관리 구문
"""

from pathlib import Path


# =========================================================
# 1. 폴더 생성
# =========================================================

# mkdir : 폴더를 만든다
#   exist_ok=True         -> 이미 있어도 에러를 내지 않음 (실습 반복 실행에 안전)
#   exist_ok=False (기본값) -> 이미 있으면 FileExistsError 발생
new_dir = Path('new_directory')
new_dir.mkdir(exist_ok=True)
print(f'폴더 준비 완료 : {new_dir}')


# =========================================================
# 2. 파일 생성 (write_text)
# =========================================================

# write_text : 문자열을 파일에 통째로 저장
#   [주의] 기존 파일이 있으면 '덮어쓰기' 됨 (append 아님!)
#   [권장] 한글 등을 다룰 땐 encoding='utf-8' 을 습관적으로 명시
Path('new_file.txt').write_text('Hello, World!', encoding='utf-8')

# 경로 결합('/')으로 '폴더 안' 파일 경로를 만든 뒤 생성
new_file = new_dir / 'new.md'
new_file.write_text('# 새로 만들기', encoding='utf-8')
print(f'파일 생성 완료 : {new_file}')


# =========================================================
# 3. 파일에 여러 줄 이어 쓰기 (open 'a' = append)
# =========================================================

# open('a') : 이어쓰기 모드. 기존 내용을 지우지 않고 '끝에 추가'
# with 구문 : 블록이 끝나면 파일을 자동으로 닫아줌 (close 깜빡할 걱정 X)
with new_file.open('a', encoding='utf-8') as file:
    file.write('\n')
    file.write('* First line\n')   # '\n' = 줄바꿈. 없으면 한 줄로 붙어버림
    file.write('* Second line\n')
    file.write('* Third line\n')

print('여러 줄 이어쓰기 완료')
print(new_file.read_text(encoding='utf-8'))  # 결과 확인용
