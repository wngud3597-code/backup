"""
02_create.py
주제: 폴더 & 파일 생성하기 (mkdir / write_text / open 'a')
수업을 따라가며 None / _____ 로 표시된 부분을 채워봅니다.
"""

from pathlib import Path


# 1. 폴더 생성
new_dir = Path('new_directory')
# [힌트] 폴더를 만드는 메서드는? (exist_ok=True: 이미 있어도 에러 없이)
new_dir.mkdir(exist_ok=True)  # TODO
print(f'폴더 준비 완료 : {new_dir}')


# 2. 파일 생성
# [힌트] 문자열을 파일에 통째로 쓰는 메서드는? (encoding 함께)
Path('new_file.txt').write_text('Hello, World!', encoding='utf-8')  # TODO

new_file = new_dir / 'new.md'  # 폴더 안 파일 경로 (경로 결합)
# [힌트] 위와 같은 메서드로 '# 새로 만들기' 저장
new_file.write_text('# 새로 만들기', encoding='utf-8')  # TODO
print(f'파일 생성 완료 : {new_file}')


# 3. 파일에 여러 줄 이어 쓰기
# [힌트] 기존 내용 '뒤에 이어서' 쓰는 모드는? ('w' 아님)
with new_file.open('a', encoding='utf-8') as file:  # TODO: 모드 채우기
    file.write('\n')
    file.write('* First line\n')
    file.write('* Second line\n')
    file.write('* Third line\n')

print('여러 줄 이어쓰기 완료')
print(new_file.read_text(encoding='utf-8'))
