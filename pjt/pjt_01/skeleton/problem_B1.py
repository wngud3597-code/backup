import json  # JSON 파일을 처리하기 위한 라이브러리
from pathlib import Path  # 파일 경로를 처리하기 위한 라이브러리

# 1. 파일 경로 설정 (books_500.json 사용)
pass  # 파일 경로 설정 부분

# 파일 존재 여부 확인
if file_path.exists():  # 파일이 존재할 경우
    # 2. 파일 열기
    pass  # 파일을 열고 JSON 데이터를 읽는 코드 (파일 열기, json.load 사용)

    # 3. 어린이 도서가 아닌 책 필터링
    non_children_books = []  # 어린이 도서가 아닌 책을 저장할 리스트
    for book in books:
        pass  # '어린이' 카테고리가 포함되지 않은 책을 필터링하는 코드

    # 4. 결과 출력
    print("어린이 도서가 아닌 책 목록:")
    for book in non_children_books:
        pass  # 도서 제목과 카테고리를 출력하는 코드
else:
    print(f"파일이 존재하지 않습니다: {file_path}")
