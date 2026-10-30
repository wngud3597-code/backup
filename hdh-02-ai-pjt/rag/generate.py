import json
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import OPENAI_API_KEY, OPENAI_CHAT_MODEL
from contracts import AnswerResult, Evidence, SentenceCitation, StatisticalResult
from rag.citations import validate_and_filter_citations

PROMPT_FILE = Path(__file__).resolve().parent.parent / "prompts" / "answer.txt"


def generate_answer_from_evidence(
    question: str, evidences: list[Evidence], stat: StatisticalResult | None
) -> AnswerResult:
    # 근거가 아예 없으면 LLM 호출 없이 즉시 보류
    if not evidences:
        return AnswerResult(
            status="insufficient",
            sentences=[
                SentenceCitation(
                    text="제공된 데이터에서 관련 정보를 찾을 수 없습니다.", citations=[]
                )
            ],
        )

    prompt_template = PROMPT_FILE.read_text(encoding="utf-8")

    # 근거 포맷팅
    evidence_payload = [
        {
            "evidence_no": e.evidence_no,
            "title": e.title,
            "text": e.text,
            "locator": e.locator,
        }
        for e in evidences
    ]

    input_payload = {"question": question, "evidence": evidence_payload}

    system_prompt = prompt_template.replace(
        "{input_json}", json.dumps(input_payload, ensure_ascii=False)
    )

    llm = ChatOpenAI(model=OPENAI_CHAT_MODEL, api_key=OPENAI_API_KEY)

    try:
        response = llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"질문: {question}"),
            ]
        )

        raw_text = response.content.strip()
        # 마크다운 코드블록 방어 처리
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        data = json.loads(raw_text)

        status = data.get("status", "answered")
        raw_sentences = [
            SentenceCitation(text=s["text"], citations=s.get("citations", []))
            for s in data.get("sentences", [])
        ]

        # 인용 일치 검증
        ev_map = {e.evidence_no: e for e in evidences}
        valid_sentences, _ = validate_and_filter_citations(raw_sentences, ev_map)

        stat_card = stat.model_dump() if stat else None

        return AnswerResult(
            status=status, sentences=valid_sentences, statistical_card=stat_card
        )

    except Exception as e:
        import traceback

        print("\n🔥 [LLM 생성 에러 상세 원인]:")
        traceback.print_exc()  # 터미널에 진짜 원인 출력

        return AnswerResult(
            status="insufficient",
            sentences=[
                SentenceCitation(
                    text="근거 자료를 분석하여 답변을 생성하는 중 오류가 발생했습니다.",
                    citations=[],
                )
            ],
        )
