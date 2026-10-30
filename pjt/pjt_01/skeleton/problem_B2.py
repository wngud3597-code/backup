import json  # JSON 파일을 처리하기 위한 라이브러리
from pathlib import Path  # 파일 경로를 처리하기 위한 라이브러리

# 1. 파일 경로 설정 (books_500.json 사용)
pass  # 파일 경로 설정 부분

# 파일 존재 여부 확인
if file_path.exists():  # 파일이 존재할 경우
    # 2. 파일 열기
    pass  # 파일을 열고 JSON 데이터를 읽는 코드 (파일 열기, json.load 사용)

    # 3. 출판사별 도서 수 집계
    publisher_counts = {}  # 출판사별 도서 수를 저장할 딕셔너리
    for book in books:
        pass  # 출판사별로 도서 수를 집계하는 코드

    # 4. 결과 출력
    print("출판사별 도서 수:")
    for (
        publisher,
        count,
    ) in publisher_counts.items():  # 각 출판사와 도서 수 출력
        pass  # 도서 수를 출력하는 코드 (print(f"{publisher}: {count}권"))
else:
    print(f"파일이 존재하지 않습니다: {file_path}")
