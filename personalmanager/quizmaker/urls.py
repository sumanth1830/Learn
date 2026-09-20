from django.urls import include, path
from . import views
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy

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
    path("flashcard/<int:pk>/review/", views.flashcard_review_submit_view, name="flashcard_review_submit"),

    path("quizhistorylist/delete/<pk>/", views.QuizHistoryDelete.as_view(), name="quiz_history_delete"),
    path("quiz/<int:pk>/create-flashcards", views.create_flashcards_from_quiz, name="create_flashcards_from_quiz"),
    path("quizzes/", views.quizzes_view, name="quizzes"),

    # News Ingestion
    path("current-affairs/", views.current_affairs_digest_view, name="current_affairs"),
    path("current-affairs/articles/", views.current_affairs_articles_view, name="current_affairs_articles"),
    path("current-affairs/<str:date>/generate-quiz/", views.generate_digest_quiz_view, name="generate_digest_quiz"),


    # Topic Brief
    path("topics-preview/", views.topics_preview_list_view, name="topics_preview_list"),
    path("topics-preview/<int:pk>/", views.topics_preview_detail_view, name="topics_preview_detail"),
    path("topics-preview/generate/", views.generate_topics_preview_view, name="generate_topics_preview"),
    path("topics-preview/<int:pk>/rate/", views.rate_topics_preview_view, name="rate_topics_preview"),
    # Login

    # path("logout/", views.logout_view, name="logout"),
    path("signup/", views.SignUp.as_view(), name="signup"),
    path("profile/", views.profile_view, name="profile"),
    path(
        "account/password_reset/",
        auth_views.PasswordResetView.as_view(
            success_url=reverse_lazy("quiz:password_reset_done"),
            html_email_template_name="registration/password_reset_email_html.html",
        ),
        name="password_reset",
    ),
    path(
        "account/reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(success_url=reverse_lazy("quiz:password_reset_complete")),
        name="password_reset_confirm",
    ),
    path("account/", include("django.contrib.auth.urls")),

    # Utility Feature links
    path("pdf-split/", views.pdf_split_view, name="pdf_split"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
]