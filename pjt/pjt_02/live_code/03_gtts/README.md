# 013. Text-to-Speech (TTS) 실습

텍스트를 음성 파일(MP3)로 바꾸는 두 가지 방법을 비교합니다.

## 📁 파일 구성

| 파일 | 내용 | 키 필요 |
| --- | --- | --- |
| `01_gtts.py` | gTTS 로 무료 음성 합성 + 옵션 비교 | ❌ |
| `02_google_cloud_tts.py` | Google Cloud TTS 로 목소리·속도 지정 | ✅ |
| `.env.example` | 필요한 환경 변수 목록 (복사해서 `.env` 로 사용) | — |

## ⚙️ 준비

```bash
# 1) 가상환경 활성화 후 라이브러리 설치
pip install gTTS google-cloud-texttospeech python-dotenv

# 2) 환경 변수 파일 준비 (02번 실습에만 필요)
copy .env.example .env    # Windows
cp .env.example .env      # macOS
```

## 🔍 gTTS vs Google Cloud TTS

| 항목 | gTTS | Google Cloud TTS |
| --- | --- | --- |
| 비용 | 무료 | 종량제 (무료 할당량 있음) |
| 인증 | 불필요 | API 키 / 서비스 계정 |
| 목소리 선택 | ❌ 불가 | ✅ 언어별 다수 |
| 속도·음높이 조절 | 느리게(`slow`)만 | ✅ 세밀하게 |
| 안정성 | 비공식 엔진, 차단 가능 | 공식 SLA |
| 용도 | 학습·프로토타입 | 실서비스 |

> 💡 **선택 기준**
> "지금 되는지 확인만 하면 된다" => gTTS
> "사용자에게 들려줄 것이다" => Cloud TTS

> ⚠️ **보안**
> API 키는 반드시 `.env` 에 두고, `.env` 는 공유하지 않습니다.
> 코드에 키를 적어 공유한 적이 있다면 그 키는 **폐기 후 재발급**하세요.

## 📚 참고 문서

- [Google Cloud Text-to-Speech 소개](https://cloud.google.com/text-to-speech?hl=ko)
- [시작하기 전에 (인증 설정)](https://cloud.google.com/text-to-speech/docs/before-you-begin?hl=ko)
- [Python 으로 음성 만들기](https://cloud.google.com/text-to-speech/docs/create-audio?hl=ko#text-to-speech-text-python)
- [지원 목소리 목록](https://cloud.google.com/text-to-speech/docs/voices)
