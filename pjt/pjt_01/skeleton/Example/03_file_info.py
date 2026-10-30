"""
03_file_info.py
주제: 폴더/파일 목록 가져오기 & 파일·폴더 구분 (iterdir / is_file / is_dir)
None / _____ 로 표시된 부분을 채워봅니다.
"""

from pathlib import Path


current_path = Path.cwd()

# [힌트] 폴더 안 항목 목록을 하나씩 돌려주는 메서드는? (결과는 제너레이터)
print(current_path.iterdir())  # <generator object Path.iterdir at 0x00000295C6CC1460>

# [힌트] 위와 같은 메서드로 반복
for item in current_path.iterdir():  # TODO
    print(item)
    # [힌트] 경로에서 '이름만' 주는 속성은?
    print(item.name)  # TODO
    print('-----')


# 파일 / 폴더 구분하기 (제너레이터가 소진됐으므로 다시 호출)
for item in current_path.iterdir():  # TODO
    # [힌트] 파일이면 True / 폴더면 True 인 메서드는?
    if item.is_file():      # TODO: 파일 여부
        print(f'파일 : {item.name}')
    elif item.is_dir():    # TODO: 폴더 여부
        print(f'폴더 : {item.name}')
    else:
        print(item.name)
