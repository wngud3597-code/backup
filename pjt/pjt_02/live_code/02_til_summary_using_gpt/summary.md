핵심 키워드
- 변수와 메모리 관리
- 데이터 타입과 동적 타이핑
- 스코프(범위)와 불변/가변성
- 리스트와 시퀀스 조작
- 함수의 구성과 재사용

주제별 재구성 요약

1) 변수와 메모리 관리
- 변수: 파이썬에서 변수는 객체를 가리키는 참조(reference)입니다.
- 메모리 관리: 파이썬은 자동으로 메모리를 할당하고, 더 이상 필요 없으면 가비지 컬렉터가 해제합니다.
- 변수 이름: 의미 있고 설명적인 이름을 사용하는 것이 좋습니다.

예시
- x = 10
- name = "Alice"

2) 데이터 타입과 동적 타이핑
- 파이썬은 동적 타이핑 언어이지만, 변수는 각각 특정 타입을 가집니다.
- 기본 타입 예시: 정수 int, 실수 float, 문자열 str, 불리언 bool
- 타입 확인: type(x)로 변수의 타입을 확인합니다.

예시
- x = 10
- print(type(x))  # <class 'int'>

3) 변수 스코프와 가변성/불변성
- 글로벌 변수(global): 함수 외부에서 정의되어 프로그램 전체에서 접근 가능
- 로컬 변수(local): 함수 내부에서 정의되어 해당 함수 내에서만 접근 가능
- 불변(immutable) 타입: int, float, str, tuple
- 가변(mutable) 타입: list, dict, set
- 주의: 불변 타입은 같은 값을 재할당해도 참조가 바뀌지 않고, 가변 타입은 원소를 바꾸면 다른 참조도 함께 바뀔 수 있습니다.

예시
- 전역 변수: global_var = 10
- 함수 안에서 로컬 변수: def f(): local_var = 20; print(global_var, local_var)
- y = x (불변 타입: x를 바꾸면 y는 독립적으로 유지)
- list1 = [1, 2, 3]; list2 = list1; list1.append(4) → list2도 [1, 2, 3, 4]로 변경

4) 리스트 및 시퀀스 조작
- 리스트 생성: 대괄호 []로 만들고, 다양한 타입의 요소 포함 가능
- 인덱싱: 0부터 시작, 음수 인덱스는 끝에서부터
- 슬라이싱: list[start:end:step]에서 start는 포함, end는 미포함
- 리스트 메서드의 대표 예
  - append(x): 끝에 한 요소 추가
  - extend(iterable): iterable의 모든 요소를 끝에 추가
  - insert(i, x): 위치 i에 x를 삽입
  - remove(x): 값이 x인 첫 요소 제거
  - pop([i]): 위치 i의 요소를 제거하고 반환(없으면 마지막)
  - clear(): 모든 요소 제거
  - index(x), count(x): 위치/개수 검색
  - sort(), reverse(): 정렬/역순으로 정렬

예시
- fruits = ['apple', 'banana', 'orange']
- fruits.append('grape')
- fruits.insert(1, 'kiwi')
- fruits.remove('banana')
- last = fruits.pop()
- print(fruits)  # 남은 리스트

5) 조건문과 비교/논리 연산
- 구조: if, elif, else
- 비교 연산자: ==, !=, <, >, <=, >=
- 논리 연산자: and, or, not
- 조건부 표현식(삼항 연산자) 예: result = "짝수" if x % 2 == 0 else "홀수"

예시
- age = 25
- if age > 18 and age < 65:
    print("성인")
  else:
    print("미성년자/다른 범주")

- 다중 조건 확인 예시
  age = 25
  income = 50000
  if age > 18 and income > 30000:
      print("대출 가능")
  else:
      print("대출 불가능")

6) 반복문(Loops)
- for 반복문: 시퀀스나 반복 가능한 객체를 순회
- range(): 숫자 시퀀스를 만들어 반복
  - range(stop): 0부터 stop-1까지
  - range(start, stop): start부터 stop-1까지
  - range(start, stop, step): 시작/끝/간격 지정
- enumerate(): 인덱스와 값을 함께 얻고 싶을 때
- 리스트 컴프리헨션(List Comprehension): 한 줄로 리스트를 만들 때 편리
- while 반복문: 조건이 참인 동안 계속 반복
- break/continue: 반복 제어
  - break: 반복 종료
  - continue: 현재 반복 건너뛰고 다음 반복으로

예시
- for i in range(5): print(i)  # 0~4
- for index, fruit in enumerate(['apple','banana','orange']): print(index, fruit)
- squares = [x**2 for x in range(1,11)]
- even_squares = [x**2 for x in range(1,11) if x % 2 == 0]
- while count < 5: print(count); count += 1
- if i == 5: break; if i % 2 == 0: continue

7) 함수(Function) 설계와 재사용
- 함수 정의: def 키워드로 만듭니다.
- 기본 형식
  - def function_name(param1, param2, ...): 
      """문서화 문자열(선택)"""
      return result
- 매개변수 종류
  - 위치 매개변수(Positional)
  - 키워드 매개변수(Keyword)
  - 기본값 매개변수(Default)
  - 가변 위치 매개변수(*args)
  - 가변 키워드 매개변수(**kwargs)
- 반환값: return으로 반환. return이 없으면 None 반환
- 스코프(Scope)
  - 지역 변수(Local): 함수 내부에서만 접근
  - 전역 변수(Global): 함수 외부에서 정의되어 전역에서 접근
- 람다 함수(Lambda): 간단한 일회용 함수
- 재귀 함수(Recursive): 자기 자신을 호출하는 함수

예시
- def get_larger_number(a, b): return a if a > b else b
- def sum_list(numbers): return sum(numbers)
- Lambda: square = lambda x: x**2; square(5) → 25
- 재귀 예시: factorial(n): if n <= 1: return 1; return n * factorial(n-1)

실습 문항의 간단한 정리 예시
- 두 수를 입력받아 더 큰 수를 반환하는 함수
  def get_larger_number(a, b):
      return a if a > b else b

- 리스트의 모든 요소 합을 반환하는 함수
  def sum_list(numbers):
      return sum(numbers)

참고: 본 요약은 입문자가 이해하기 쉽게 핵심 개념과 자주 쓰는 예제를 정리한 것입니다. 원본 노트의 예제 중 일부는 오타나 변수 이름 불일치가 섞여 있어, 학습용으로는 정정된 형태의 예제를 함께 제시했습니다. 필요하면 특정 섹션의 예제를 더 자세히 다시 정리해 드리겠습니다.

---
> 🤖 이 문서는 AI(`gpt-5-nano`)가 자동 생성한 요약본입니다. 내용의 정확성은 반드시 사람이 검토해 주세요.
