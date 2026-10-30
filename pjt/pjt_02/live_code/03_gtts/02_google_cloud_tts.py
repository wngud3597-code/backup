'''
02_google_cloud_tts.py - Google Cloud Text-to-Speech API 사용하기

🏠 이 파일은 [선택 실습 / 과제] 입니다.
   Google Cloud 계정 생성에 결제 카드 등록이 필요해서 수업에서는 강사님의 실행 화면을 보고
   코드 구조만 함께 읽고, 실제 실행은 각자 진행합니다.
   (카드 등록은 본인 확인 목적이며, 무료 등급 안에서는 과금되지 않습니다)

🎯 학습 목표
    1) Cloud TTS 요청의 3요소(입력 / 목소리 / 출력 형식)를 나눠 구성한다.
    2) 텍스트 응답과 바이너리(오디오) 응답의 저장 방식 차이를 이해한다.

📝 결과물
    목소리와 속도를 직접 지정해 고품질 음성 파일을 만든다.

📌 gTTS = 길거리 무료 시식 / Cloud TTS = 정식 계약한 성우
    시식은 못 고르고, 성우는 값을 치르는 대신 고를 수 있습니다.

📌 준비
    1) Google Cloud Console 에서 Text-to-Speech API 사용 설정 + API 키 발급
       https://console.cloud.google.com
    2) .env.example 을 복사해 .env 로 만들고 키를 입력
       (GOOGLE_TTS_API_KEY=발급받은_키)
    3) pip install google-cloud-texttospeech python-dotenv

⚠️ API 키를 소스 코드에 직접 적으면 파일을 공유하는 순간 키가 유출됩니다.
   반드시 .env 로 분리하세요.

📌 실습 TODO : 4개
'''

import os
from pathlib import Path

from dotenv import load_dotenv
from google.api_core.client_options import ClientOptions
from google.cloud import texttospeech

# ---------------------------------------------------------------------------
# 1. 인증 설정 (API 키 방식)
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')

# TODO 1: .env 에서 GOOGLE_TTS_API_KEY 값을 읽어오세요.
API_KEY = os.getenv('GOOGLE_TTS_API_KEY')

if not API_KEY:
    raise SystemExit(
        'GOOGLE_TTS_API_KEY 를 찾을 수 없습니다. .env 를 확인하세요.'
    )

# 발급받은 키를 클라이언트 옵션에 담아 전달합니다. (여기는 완성되어 있습니다)
client_options = ClientOptions(api_key=API_KEY)
client = texttospeech.TextToSpeechClient(client_options=client_options)


# ---------------------------------------------------------------------------
# 2. 요청 3종 구성 - 성우에게 녹음을 맡기는 과정
# ---------------------------------------------------------------------------
# [실습 포인트] Cloud TTS 는 "무엇을 / 누가 / 어떤 형식으로" 를 나눠 지정합니다.

# (1) 무엇을 읽을 것인가 - 성우에게 건네는 대본
# TODO 2: SynthesisInput 으로 읽을 문장을 지정하세요.
#   힌트: texttospeech.SynthesisInput(text='...')
synthesis_input = texttospeech.SynthesisInput(
    text='안녕하세요 저는 구글 클라우드 TTS 서비스 입니다.'
)

# (2) 누가 읽을 것인가 - 언어/성별/목소리 이름을 지정해 성우를 고르는 단계
#     목소리 목록: https://cloud.google.com/text-to-speech/docs/voices
# TODO 3: VoiceSelectionParams 로 목소리를 지정하세요.
#   힌트: texttospeech.VoiceSelectionParams(
#             language_code='ko-KR', name='ko-KR-Standard-A')
voice = texttospeech.VoiceSelectionParams(
    language_code='ko-KR',  # 언어 코드
    ssml_gender=texttospeech.SsmlVoiceGender.FEMALE,  # 성별
    name='ko-KR-Standard-A',  # 목소리 이름
)

# (3) 어떤 형식으로 받을 것인가 - 파일 포맷/속도 (여기는 완성되어 있습니다)
audio_config = texttospeech.AudioConfig(
    audio_encoding=texttospeech.AudioEncoding.MP3,
    speaking_rate=1.0,  # 0.25 ~ 4.0
)


# ---------------------------------------------------------------------------
# 3. API 호출 및 저장
# ---------------------------------------------------------------------------
print('🔊 Google Cloud TTS 에 음성 합성을 요청합니다...')

# TODO 4: 3종을 넘겨 음성 합성을 요청하고 결과를 response 에 담으세요.
#   힌트: client.synthesize_speech(
#             input=synthesis_input, voice=voice, audio_config=audio_config)
response = client.synthesize_speech(
             input=synthesis_input, voice=voice, audio_config=audio_config)

# [실습 포인트] 응답은 텍스트가 아니라 '바이너리(오디오 바이트)'입니다.
#   그래서 'w'(텍스트 쓰기)가 아니라 'wb'(바이너리 쓰기)로 열어야 합니다.
#   'w' 로 열면 TypeError 가 납니다. 한 번 일부러 바꿔서 에러를 확인해 보세요.
output_path = BASE_DIR / 'speech_google_cloud.mp3'

with output_path.open('wb') as out:
    out.write(response.audio_content)

print(f'✅ 저장 완료 : {output_path.name}')


# ---------------------------------------------------------------------------
# 🚀 도전 과제
#   1) 목소리 이름을 'ko-KR-Neural2-A' 로 바꿔 저장하고,
#      Standard 버전과 소리를 비교해 보세요.
#   2) speaking_rate 를 0.75 / 1.5 로 바꿔 어떤 차이가 있는지 들어보세요.
#   3) 01번 gTTS 결과와 02번 Cloud TTS 결과를 나란히 듣고,
#      어떤 상황에 무엇을 쓸지 표로 정리해 보세요.
# ---------------------------------------------------------------------------
