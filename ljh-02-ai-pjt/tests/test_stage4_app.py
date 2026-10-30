"""Stage 4 UI regressions; test answers and sources never enter production."""

from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


PROJECT = Path(__file__).resolve().parents[1]
MOVIE_A, MOVIE_B = "753091", "17431"


class FakeRagService:
    def __init__(self):
        self.calls = []
        self.results = []
        self.fail_next = False
        self.next_semantic_check = None
        self.next_checks = None
        self.next_external_error = None

    def answer(self, movie, question, history, mode="general", refresh=False):
        self.calls.append({"movie_id": movie.movie_id, "question": question,
                           "history": deepcopy(history), "mode": mode, "refresh": refresh})
        if self.fail_next:
            self.fail_next = False
            return {"content": "", "sources": [], "error": {"category": "격리된 생성 실패"}}
        number = len(self.results) + 1
        result = {"content": f"격리된 테스트 답변 {number}입니다. [근거 1]",
                  "sources": [{"title": f"격리된 출처 {movie.movie_id}-{number}",
                               "url": f"https://example.org/{movie.movie_id}/{number}",
                               "quote": f"테스트 근거 구절 {number}", "movie_id": movie.movie_id}],
                  "retrieval": {"diagnostics": {"warnings": []}}}
        if self.next_semantic_check is not None:
            result["validation"] = {"semantic_check": self.next_semantic_check}
            if self.next_semantic_check == "item_review_held":
                result["content"] = "**작품 속 묘사 · 검토 보류**\n\n격리된 테스트의 항목 판정을 보류했습니다."
                result["sources"] = []
            elif self.next_semantic_check == "no_factual_assertions":
                result["content"] = "격리된 테스트의 질문을 확인할 근거가 부족합니다."
                result["sources"] = []
            elif self.next_semantic_check == "item_review_partial":
                result["content"] += "\n\n**작품 속 묘사 · 검토 보류**\n\n이 항목의 검토를 보류했습니다."
            self.next_semantic_check = None
        if self.next_checks is not None:
            result["checks"] = self.next_checks
            self.next_checks = None
        if self.next_external_error is not None:
            result["retrieval"]["diagnostics"]["external_error"] = self.next_external_error
            self.next_external_error = None
        self.results.append(result)
        return result


class Stage4AppTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch("socket.socket.connect", side_effect=AssertionError("Offline Stage 4 UI test")))
        self.service = FakeRagService()
        self.stack.enter_context(patch("movie_lab.rag.create_rag_service", return_value=self.service))
        self.stack.enter_context(patch("movie_lab.config.resolve_movies_path", return_value=PROJECT / "data/movies.json"))
        self.stack.enter_context(patch("movie_lab.index.inspect_index_status", return_value={"state": "ready", "count": 964}))

    def app(self):
        app = AppTest.from_file(str(PROJECT / "app.py"), default_timeout=15).run()
        self.assertFalse(app.exception)
        return app

    def test_main_chat_answer_snapshots_survive_rerun_and_movie_switch_with_verify_mode(self):
        app = self.app()
        app.selectbox(key="selected_movie_id").select(MOVIE_A).run()
        app.chat_input(key="question").set_value("첫 번째 질문").run()
        self.assertFalse(app.exception)
        first_title = self.service.results[0]["sources"][0]["title"]
        first_url = self.service.results[0]["sources"][0]["url"]
        first_id = app.session_state["threads_by_movie"][MOVIE_A][1]["answer_id"]
        self.service.results[0]["sources"][0]["title"] = "나중에 변경된 원본 객체"
        app.run()
        self.assertEqual(len(self.service.calls), 1)
        self.assertEqual(len(app.session_state["threads_by_movie"][MOVIE_A]), 2)
        rendered = "\n".join(row.value for row in app.markdown)
        self.assertIn(first_title, rendered)
        self.assertIn(first_url, rendered)
        self.assertNotIn("나중에 변경된 원본 객체", rendered)

        app.radio(key="answer_mode").set_value("작품·현실 배경 확인").run()
        app.chat_input(key="question").set_value("두 번째 확인 주장").run()
        self.assertEqual(self.service.calls[-1]["mode"], "verify")
        self.assertEqual(len(self.service.calls[-1]["history"]), 3)
        second_title = self.service.results[1]["sources"][0]["title"]
        app.selectbox(key="selected_movie_id").select(MOVIE_B).run()
        app.chat_input(key="question").set_value("다른 영화 질문").run()
        other_title = self.service.results[2]["sources"][0]["title"]
        app.selectbox(key="selected_movie_id").select(MOVIE_A).run()
        app.run()
        self.assertFalse(app.exception)
        rendered = "\n".join(row.value for row in app.markdown)
        self.assertIn(first_title, rendered)
        self.assertIn(second_title, rendered)
        self.assertNotIn(other_title, rendered)
        self.assertEqual(len(self.service.calls), 3)
        self.assertEqual(len(app.session_state["threads_by_movie"][MOVIE_A]), 4)
        self.assertEqual(len(app.session_state["threads_by_movie"][MOVIE_B]), 2)
        self.assertEqual(app.session_state["threads_by_movie"][MOVIE_A][1]["answer_id"], first_id)
        previous_thread = deepcopy(app.session_state["threads_by_movie"][MOVIE_A])
        self.service.next_semantic_check = "item_review_held"
        app.chat_input(key="question").set_value("검토 보류가 필요한 후속 주장").run()
        self.assertFalse(app.exception)
        held_status = next(row for row in app.status if row.label == "판정 검토 보류")
        self.assertEqual(held_status.state, "error")
        self.assertEqual(app.session_state["threads_by_movie"][MOVIE_A][:4], previous_thread)
        self.assertIn("검토 보류", app.session_state["threads_by_movie"][MOVIE_A][-1]["content"])
        self.assertEqual(app.session_state["threads_by_movie"][MOVIE_A][-1]["sources"], [])
        app.run()
        self.assertEqual(app.session_state["threads_by_movie"][MOVIE_A][:4], previous_thread)
        self.assertEqual(len(self.service.calls), 4)

    def test_failed_answer_retry_does_not_duplicate_user_question(self):
        app = self.app()
        app.selectbox(key="selected_movie_id").select(MOVIE_A).run()
        self.service.fail_next = True
        app.chat_input(key="question").set_value("다시 확인할 질문").run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state["threads_by_movie"][MOVIE_A]), 1)
        self.assertEqual(app.session_state["threads_by_movie"][MOVIE_A][0]["role"], "user")
        self.assertIn("격리된 생성 실패", app.error[0].value)
        self.assertTrue(any(status.label == "답변 생성 실패" and status.state == "error" for status in app.status))
        app.run()
        app.button(key="retry_answer").click().run()
        self.assertFalse(app.exception)
        thread = app.session_state["threads_by_movie"][MOVIE_A]
        self.assertEqual([row["role"] for row in thread], ["user", "assistant"])
        self.assertEqual([row["content"] for row in thread if row["role"] == "user"], ["다시 확인할 질문"])
        self.assertEqual(len(self.service.calls), 2)
        self.assertEqual(self.service.calls[0]["question"], self.service.calls[1]["question"])
        app.run()
        self.assertEqual(len(self.service.calls), 2)
        self.assertEqual(len(app.session_state["threads_by_movie"][MOVIE_A]), 2)

    def test_first_use_guidance_selected_identity_mode_and_collapsed_advanced_settings(self):
        app = self.app()
        self.assertTrue(any("영화를 고르면" in item.value and "답변의 원문" in item.value for item in app.markdown))
        self.assertTrue(any(item.label == "자연어로 영화 찾기" for item in app.expander))
        self.assertEqual(len(self.service.calls), 0)
        app.selectbox(key="selected_movie_id").select(MOVIE_A).run()
        identity = app.subheader[0].value
        for fragment in ("더 문", "2023"):
            self.assertIn(fragment, identity)
        rendered = "\n".join(row.value for row in app.markdown)
        self.assertIn("**감독** 김용화", rendered)
        self.assertIn(f"영화 ID: {MOVIE_A}", rendered)
        self.assertTrue(any("선택한 영화" == item.value for item in app.caption))
        advanced = next(item for item in app.expander if item.label == "고급 설정 · 자료 미리 준비")
        plot = next(item for item in app.expander if item.label == "줄거리 보기 · 스포일러 포함 가능")
        self.assertFalse(advanced.proto.expanded)
        self.assertFalse(plot.proto.expanded)
        self.assertEqual(app.radio(key="answer_mode").value, "근거 기반 질문")
        self.assertTrue(any("아래 질문창에 궁금한 점" in item.value for item in app.caption))
        app.radio(key="answer_mode").set_value("작품·현실 배경 확인").run()
        self.assertEqual(app.radio(key="answer_mode").value, "작품·현실 배경 확인")
        self.assertTrue(any("확인할 주장을 적어주세요" in item.value for item in app.caption))
        self.assertEqual(len(self.service.calls), 0)

    def test_success_insufficient_partial_and_held_results_have_distinct_statuses(self):
        app = self.app()
        app.selectbox(key="selected_movie_id").select(MOVIE_A).run()
        app.radio(key="answer_mode").set_value("작품·현실 배경 확인").run()
        cases = (("item_review_passed", "답변과 인용 확인 완료", False),
                 ("item_review_passed", "일부 확인 · 근거 부족 포함", True),
                 ("no_factual_assertions", "근거 부족 안내", True),
                 ("item_review_partial", "일부 항목 검토 보류", True),
                 ("item_review_held", "판정 검토 보류", True))
        for number, (semantic_check, expected_label, has_insufficient) in enumerate(cases, 1):
            with self.subTest(semantic_check=semantic_check, has_insufficient=has_insufficient):
                previous = deepcopy(app.session_state["threads_by_movie"].get(MOVIE_A, []))
                self.service.next_semantic_check = semantic_check
                self.service.next_checks = [{"scope": "작품 속 묘사", "claim": "격리된 감독 주장",
                                             "verdict": "근거 부족", "reason": "현재 근거로 확인하지 못했습니다."}] if has_insufficient else []
                if semantic_check == "item_review_passed" and has_insufficient:
                    self.service.next_checks.append({"scope": "현실 사실", "claim": "격리된 배경 주장",
                                                     "verdict": "확인됨", "reason": "격리된 출처에서 확인했습니다."})
                    self.service.next_external_error = {"category": "API 서버 오류", "status_code": 502}
                app.chat_input(key="question").set_value(f"격리된 상태 확인 {number}").run()
                self.assertFalse(app.exception)
                status = next(item for item in app.status if item.label == expected_label)
                self.assertEqual(status.state, "error" if semantic_check == "item_review_held" else "complete")
                thread = app.session_state["threads_by_movie"][MOVIE_A]
                self.assertEqual(thread[:len(previous)], previous)
                self.assertEqual(len(thread), len(previous) + 2)
                if semantic_check == "no_factual_assertions":
                    self.assertTrue(any("근거 부족을 거짓으로 판정하지 않습니다" in item.value for item in app.info))
                elif semantic_check == "item_review_passed" and has_insufficient:
                    self.assertTrue(any("일부 항목은 현재 확보한 근거로 확인하지 못했습니다" in item.value for item in app.info))
                    self.assertTrue(any("근거 검색 연결에 실패해 저장된 자료로 답했습니다" in item.value for item in app.warning))
                    self.assertFalse(any("근거 검색 연결에 실패" in item.value for item in status.warning))
                    self.assertEqual(thread[-1]["sources"], self.service.results[-1]["sources"])
                elif semantic_check == "item_review_partial":
                    self.assertTrue(any("보류한 항목에는 근거를 붙이지 않습니다" in item.value for item in app.warning))
                elif semantic_check == "item_review_held":
                    self.assertTrue(any("주장이 거짓이라는 뜻은 아닙니다" in item.value for item in app.warning))
        self.assertEqual(len(self.service.calls), len(cases))


if __name__ == "__main__":
    unittest.main()
