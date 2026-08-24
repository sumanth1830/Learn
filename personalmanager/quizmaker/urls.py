from django.urls import include, path
from . import views

app_name="quiz"

urlpatterns = [
    path("", views.home, name="home"),
    # path("quizlist/", views.QuizList.as_view(), name="quiz_list"),
    # path("quizlist/update/<pk>", views.QuizUpdate.as_view(), name="quiz_update"),
    # path("quizlist/delete/<pk>", views.QuizDelete.as_view(), name="quiz_delete"),
    path("flashcard/list/", views.FlashCardList.as_view(), name="flashcard_list"),
    path("flashcard/create", views.FlashCardCreate.as_view(), name="flashcard_create"),
    path("flashcard/update/<pk>", views.FlashCardUpdate.as_view(), name="quiz_update"),
    path("flashcard/delete/<pk>", views.FlashCardDelete.as_view(), name="quiz_delete"),
    path("quizhistory/list/", views.QuizHistoryList.as_view(), name="quiz_history_list"),
    path("quizhistorylist/delete/<pk>", views.QuizHistoryDelete.as_view(), name="quiz_history_delete"),

    # Login
    path("account/", include("django.contrib.auth.urls")),
    path("logout/", views.logout_view, name="logout"),
    path("signup/", views.SignUp.as_view(), name="signup")
]