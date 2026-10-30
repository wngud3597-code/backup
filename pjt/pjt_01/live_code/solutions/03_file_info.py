"""
03_file_info.py
주제: 폴더/파일 목록 가져오기 & 파일·폴더 구분 (iterdir / is_file / is_dir)

핵심 개념
  - iterdir()  : 폴더 '바로 아래' 항목(파일/폴더)을 하나씩 돌려주는 제너레이터
                 (하위 폴더 내부까지는 들어가지 않음)
  - 제너레이터 : 값을 미리 다 만들지 않고 '필요할 때 하나씩' 꺼내주는 지연(lazy) 객체
                 -> 한 번 순회하면 소진됨. 다시 쓰려면 iterdir()를 다시 호출
  - is_file() / is_dir() : 해당 경로가 파일이면 / 폴더이면 True
"""

from pathlib import Path


current_path = Path.cwd()

# iterdir() 자체는 '제너레이터 객체'를 반환 (목록이 바로 보이지 않음)
print(current_path.iterdir())  # <generator object Path.iterdir at 0x...>


# 반복문으로 하나씩 꺼내 확인
for item in current_path.iterdir():
    print(item)        # 전체 경로
    print(item.name)   # 이름만
    print('-----')


# 파일 / 폴더 구분하기
# (iterdir()를 다시 호출: 위 반복문에서 제너레이터가 이미 소진됐기 때문)
for item in current_path.iterdir():
    if item.is_file():
        print(f'파일 : {item.name}')
    elif item.is_dir():
        print(f'폴더 : {item.name}')
    else:
        print(item.name)
