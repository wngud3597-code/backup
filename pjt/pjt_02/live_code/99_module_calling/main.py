'''파일명: main.py

my_module 을 '부품'으로 가져다 쓰는 파일.

    $ python main.py

📌 이 폴더는 채울 빈칸이 없습니다. 실행해서 출력을 비교하는 것이 목적입니다.
'''

# import 하는 순간 my_module.py 의 최상위 코드가 한 번 실행된다
import my_module

# 같은 my_module.py 인데, 직접 실행할 때와 import 될 때 __name__ 이 달라진다
print('[main] __name__ =', __name__)
print('[main] my_module.__name__ =', my_module.__name__)

print(my_module.greet('교육생'))


# ---------------------------------------------------------------------------
# 🔎 예상 출력
#   [my_module] __name__ = my_module        <- import 되며 최상위 코드가 실행됨
#   [main] __name__ = __main__              <- 지금 주인공은 main.py
#   [main] my_module.__name__ = my_module   <- my_module 은 부품
#   안녕하세요, 교육생님!
#
#   * my_module.py 의 '실행 가드 안쪽'은 출력되지 않는다는 점에 주목하세요.
# ---------------------------------------------------------------------------
