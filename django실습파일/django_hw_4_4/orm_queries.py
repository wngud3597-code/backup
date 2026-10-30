from datetime import time

from garages.models import Garage

# 1. 독도에 있는 차고지를 조회하고, 없다면 생성한다.
dokdo_garages = Garage.objects.filter(location="독도")
if not dokdo_garages.exists():
    Garage.objects.create(
        location="독도",
        capacity=50,
        is_parking_avaliable=True,
        opening_time=time(8, 0),
        closing_time=time(22, 0),
    )
    dokdo_garages = Garage.objects.filter(location="독도")
print(dokdo_garages)

# 2. 수용 가능 대수가 30 이하인 차고지를 모두 출력한다.
small_garages = Garage.objects.filter(capacity__lte=30)
print(small_garages)

# 3. 주차 가능한 차고지를 조회하고 각각의 위치를 출력한다.
available_garages = Garage.objects.filter(is_parking_avaliable=True)
for garage in available_garages:
    print(garage.location)
