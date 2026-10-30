import json  # JSON 데이터를 처리하기 위한 라이브러리
from pathlib import Path  # 파일 경로 처리를 위한 라이브러리

# 1. 파일 경로 설정
# pathlib을 사용하여 파일 경로를 설정합니다.
file_path = Path('./data/books_20.json')  # 파일 경로 설정

# 2. 파일 존재 여부 확인
# 파일이 존재하는지 확인하고, 존재하면 파일을 열어 JSON 데이터를 읽습니다.
if file_path.exists():  # 파일 존재 여부 확인
    # 파일 열기
    with file_path.open('r', encoding='utf-8') as file:
        pass  # JSON 파일을 파이썬 딕셔너리로 변환하는 코드 (json.load)

    # 3. 책 제목 리스트 생성
    # 'item' 항목을 순회하며 각 도서의 'title' 값을 리스트에 추가합니다.
    book_titles = []  # 책 제목을 저장할 빈 리스트
    for item in data['item']:  # 'item' 리스트에서 각 항목을 순회
        pass  # 책 제목을 리스트에 추가하는 코드 (book_titles.append)

    # 4. 결과 출력
    # 리스트에 저장된 책 제목을 출력합니다.
    print("책 제목 리스트:")
    pass  # 책 제목을 출력하는 코드 (print(book_titles))

else:
    # 5. 파일이 없을 경우 처리
    # 파일이 존재하지 않으면 오류 메시지를 출력합니다.
    pass  # 파일이 존재하지 않을 때의 처리 코드 (print(f"파일이 존재하지 않습니다: {file_path}"))
