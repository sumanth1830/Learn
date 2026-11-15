import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Answer, FlashCard, Question, Quiz, QuizAttemptAnswer, QuizHistory, GameProfile, VillageArea
from .views.game_api import _chapter_key

TOPIC = "Ch 6: The Beginnings of Indian Civilisation"


class GameApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("player", password="pw-for-tests-only")
        self.other = User.objects.create_user("other", password="pw-for-tests-only")
        self.client.force_login(self.user)
        self.quiz = Quiz.objects.create(
            quiz_name="Ch6", quiz_topic=TOPIC, max_questions=2, creator=self.user,
            status="READY", exam_name="GRADE_12_BELOW")
        self.questions = []
        for i in range(2):
            q = Question.objects.create(
                question_text=f"Q{i}", topic=TOPIC, question_type="MCQ",
                creator=self.user, quiz=self.quiz, hint="h", explanation="e")
            answers = [Answer.objects.create(question=q, answer_text=f"A{j}",
                                             is_correct=(j == 1), is_option=True)
                       for j in range(4)]
            self.questions.append((q, answers))
        for i in range(4):
            FlashCard.objects.create(front_text=f"F{i}", explanation="B", topic=TOPIC,
                                     creator=self.user, correct_streak=i,
                                     last_reviewed_at=timezone.now())

    def test_chapter_key_formats(self):
        for topic in ["Ch 4: Timeline", "Chapter 4", "Ch.4", "ch4"]:
            self.assertEqual(_chapter_key(topic), "ch4")
        self.assertEqual(_chapter_key("Sample"), "")
        self.assertEqual(_chapter_key("Tech 5"), "")

    def test_state_lists_chapter_and_decays_with_sim_days(self):
        data = self.client.get(reverse("quiz:game_state")).json()
        ch = data["chapters"][0]
        self.assertEqual((ch["key"], ch["quiz_id"], ch["num_cards"]), ("ch6", self.quiz.pk, 4))
        self.assertEqual(ch["num_overdue"], 0)
        # streaks 0..3 are due after 1, 2, 4, 8 days
        later = self.client.get(reverse("quiz:game_state"), {"sim_days": 3}).json()
        self.assertEqual(later["chapters"][0]["num_overdue"], 2)

    def test_quiz_payload_has_four_options_and_correct_id(self):
        data = self.client.get(reverse("quiz:game_quiz", args=[self.quiz.pk])).json()
        q = data["questions"][0]
        self.assertEqual(len(q["options"]), 4)
        self.assertEqual(q["correct_id"], self.questions[0][1][1].pk)

    def test_submit_saves_history_and_scores_on_server(self):
        q0, a0 = self.questions[0]
        q1, a1 = self.questions[1]
        body = {"answers": [{"question_id": q0.pk, "answer_id": a0[1].pk},
                            {"question_id": q1.pk, "answer_id": a1[0].pk}]}
        resp = self.client.post(reverse("quiz:game_quiz_submit", args=[self.quiz.pk]),
                                json.dumps(body), content_type="application/json")
        self.assertEqual(resp.json()["num_correct"], 1)
        self.assertEqual(QuizHistory.objects.get().num_wrong, 1)
        self.assertEqual(QuizAttemptAnswer.objects.count(), 2)

    def test_review_at_sim_date_clears_overdue(self):
        card = FlashCard.objects.get(front_text="F0")
        self.client.post(reverse("quiz:game_flashcard_review", args=[card.pk]),
                         json.dumps({"mastered": True, "sim_days": 5}),
                         content_type="application/json")
        card.refresh_from_db()
        self.assertEqual(card.correct_streak, 1)
        self.assertGreater(card.last_reviewed_at, timezone.now() + timedelta(days=4))
        cards = self.client.get(reverse("quiz:game_flashcards"),
                                {"topic": TOPIC, "sim_days": 5}).json()["cards"]
        self.assertFalse(next(c for c in cards if c["id"] == card.pk)["overdue"])

    def test_other_users_quiz_is_hidden(self):
        self.client.force_login(self.other)
        resp = self.client.get(reverse("quiz:game_quiz", args=[self.quiz.pk]))
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(self.client.get(reverse("quiz:game_state")).json()["chapters"], [])

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("quiz:game_state")).status_code, 302)

    def _submit(self, right_count):
        answers = []
        for i, (q, a) in enumerate(self.questions):
            answers.append({"question_id": q.pk, "answer_id": (a[1] if i < right_count else a[0]).pk})
        return self.client.post(reverse("quiz:game_quiz_submit", args=[self.quiz.pk]),
                                json.dumps({"answers": answers}),
                                content_type="application/json").json()

    def test_coins_only_for_improvement(self):
        first = self._submit(1)                     # 1/2 right, first try
        self.assertEqual(first["coins_earned"], 10)
        again = self._submit(1)                     # same score: nothing new
        self.assertEqual(again["coins_earned"], 0)
        perfect = self._submit(2)                   # +1 right and a perfect run
        self.assertEqual(perfect["coins_earned"], 10 + 30)
        self.assertEqual(GameProfile.objects.get(user=self.user).coins, 50)

    def test_wrong_answers_damage_the_area(self):
        result = self._submit(0)                    # both wrong, no cards overdue: strength 1
        self.assertAlmostEqual(result["area_loss"], 0.30, places=3)
        area = VillageArea.objects.get(user=self.user, chapter_key="ch6")
        self.assertAlmostEqual(area.base_health, 0.70, places=3)

    def test_state_area_health_combines_damage_and_neglect(self):
        self._submit(0)                                   # base health 1.0 -> 0.70
        ch = self.client.get(reverse("quiz:game_state"), {"sim_days": 3}).json()["chapters"][0]
        # 2 of 4 cards overdue at +3 days: 0.70 - 0.40 * 0.5 = 0.50
        self.assertAlmostEqual(ch["area_base_health"], 0.70, places=3)
        self.assertAlmostEqual(ch["area_health"], 0.35, places=3)
        self.assertEqual(ch["quizzes"][0]["best_score"], 0)
        self.assertFalse(ch["quizzes"][0]["perfect"])


    def test_repair_spends_coins_and_caps_at_full(self):
        self._submit(0)                                   # area 1.0 -> 0.70, earns 0 coins
        url = reverse("quiz:game_area_repair", args=["ch6"])
        self.assertEqual(self.client.post(url).status_code, 400)   # no coins yet
        GameProfile.objects.filter(user=self.user).update(coins=25)
        result = self.client.post(url).json()
        self.assertEqual(result["coins_total"], 15)
        self.assertAlmostEqual(result["area_base_health"], 0.75, places=3)
        self.client.post(reverse("quiz:game_reset"))
        self.assertEqual(self.client.post(url).status_code, 400)   # full after reset
        self.assertEqual(GameProfile.objects.get(user=self.user).coins, 100)