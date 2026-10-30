'''파일명: my_module.py

🎯 학습 목표
    `__name__` 이라는 내장 변수가 '실행 방식'에 따라 어떻게 바뀌는지 눈으로 확인한다.

핵심 한 줄
    __name__ 은 "지금 이 파일이 주인공인가, 부품인가"를 알려주는 이름표다.
      - 직접 실행(python my_module.py)  => '__main__'
      - import 되어 부품으로 쓰임        => 'my_module' (모듈 이름)

📌 이 폴더는 채울 빈칸이 없습니다. 아래 두 명령을 각각 실행하고
   출력이 어떻게 달라지는지 비교해 보세요.

    $ python my_module.py
    $ python main.py
'''

# 최상위 코드: 직접 실행할 때도, import 될 때도 항상 실행된다
print('[my_module] __name__ =', __name__)


def greet(name):
    return f'안녕하세요, {name}님!'


# 실행 가드: 이 파일을 '직접 실행'할 때만 실행된다
# (언더바는 앞뒤로 2개씩 = __main__)
if __name__ == '__main__':
    print('[my_module] 실행 가드 안쪽 실행됨')
    print(greet('SSAFY'))


# ---------------------------------------------------------------------------
# 🔎 확인 포인트
#   $ python my_module.py
#       [my_module] __name__ = __main__        <- 내가 주인공
#       [my_module] 실행 가드 안쪽 실행됨        <- 가드 통과
#       안녕하세요, SSAFY님!
#
#   $ python main.py
#       [my_module] __name__ = my_module       <- 나는 부품
#       (실행 가드 안쪽은 출력되지 않음)
#
# 💡 그래서 02_TIL_summary_with_openai_function.py 도
#    if __name__ == '__main__': 아래에 실행 코드를 둡니다.
#    나중에 이 파일을 다른 곳에서 import 해도 요약이 멋대로 돌지 않게 하려고요.
# ---------------------------------------------------------------------------
