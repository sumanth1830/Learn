from django.urls import include, path
from . import views

# app's namespace
app_name="quiz"

urlpatterns = [
    path("", views.home, name="home"),
    path("quiz/create/", views.QuizCreateView.as_view(), name="quiz_create"),
    path("quiz/<int:pk>/processing/", views.quiz_processing_view, name="processing"),
    path("quiz/<int:pk>/status/", views.quiz_status_view, name="quiz_status"),
    path("quiz/<int:pk>/quiz_take/", views.quiz_take_view, name="quiz_take"),
    path("quiz/results/<int:pk>/", views.quiz_results_view, name="quiz_results"),
    path("quiz/<int:pk>/retry/", views.quiz_retry_view, name="quiz_retry"),
    path("quiz/<int:pk>/review/", views.quiz_review_submit_view, name="quiz_review_submit"),
    path("quiz/<int:pk>/flag/", views.quiz_flag_submit_view, name="quiz_flag_submit"),
    path("quiz/<int:pk>/resume/", views.quiz_resume_view, name="quiz_resume"),

    # path("flashcard/list/", views.FlashCardList.as_view(), name="flashcard_list"),
    path("flashcard/list/", views.flash_card_list_view, name="flashcard_list"),
    path("flashcard/create/", views.FlashCardCreate.as_view(), name="flashcard_create"),
    path("flashcard/update/<pk>/", views.FlashCardUpdate.as_view(), name="flashcard_update"),
    path("flashcard/delete/<pk>/", views.FlashCardDelete.as_view(), name="flashcard_delete"),
    path("flashcards/topic/<str:topic>/", views.flashcard_topic_detail_view, name="flashcard_topic"),
    path("flashcards/topic/<str:topic>/delete/", views.flashcard_topic_delete_view, name="flashcard_topic_delete"),
    path("flashcards/topic/<str:topic>/study", views.flashcard_study_view, name="flashcard_study"),

    path("quizhistory/list/", views.QuizHistoryList.as_view(), name="quiz_history_list"),
    path("quizhistorylist/delete/<pk>/", views.QuizHistoryDelete.as_view(), name="quiz_history_delete"),
    path("quiz/<int:pk>/create-flashcards", views.create_flashcards_from_quiz, name="create_flashcards_from_quiz"),

    # Login
    path("account/", include("django.contrib.auth.urls")),
    # path("logout/", views.logout_view, name="logout"),
    path("signup/", views.SignUp.as_view(), name="signup"),
    path("profile/", views.profile_view, name="profile"),

    # Utility Feature links
    path("pdf-split/", views.pdf_split_view, name="pdf_split"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
]