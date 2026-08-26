from django.urls import include, path
from . import views

app_name="quiz"

urlpatterns = [
    path("", views.home, name="home"),
    path("quiz/create/", views.QuizCreateView.as_view(), name="quiz_create"),
    path("quiz/<int:pk>/processing/", views.quiz_processing_view, name="processing"),
    path("quiz/<int:pk>/status/", views.quiz_status_view, name="quiz_status"),
    path("quiz/<int:pk>/quiz_take/", views.quiz_take_view, name="quiz_take"),
    path("quiz/results/<int:pk>/", views.quiz_results_view, name="quiz_results"),

    path("flashcard/list/", views.FlashCardList.as_view(), name="flashcard_list"),
    path("flashcard/create/", views.FlashCardCreate.as_view(), name="flashcard_create"),
    path("flashcard/update/<pk>/", views.FlashCardUpdate.as_view(), name="quiz_update"),
    path("flashcard/delete/<pk>/", views.FlashCardDelete.as_view(), name="quiz_delete"),

    path("quizhistory/list/", views.QuizHistoryList.as_view(), name="quiz_history_list"),
    path("quizhistorylist/delete/<pk>/", views.QuizHistoryDelete.as_view(), name="quiz_history_delete"),

    # Login
    path("account/", include("django.contrib.auth.urls")),
    # path("logout/", views.logout_view, name="logout"),
    path("signup/", views.SignUp.as_view(), name="signup")
]


# urlpatterns = [
#     path("", views.home, name="home"),
#     path("quiz/create/", views.QuizCreateView.as_view(), name="quiz_create"),
#     path("quiz/<int:pk>/processing/", views.quiz_processing_view, name="processing"),
#     path("quiz/<int:pk>/status/", views.quiz_status_view, name="quiz_status"),
#
#     path("flashcard/list/", views.FlashCardList.as_view(), name="flashcard_list"),
#     path("flashcard/create/", views.FlashCardCreate.as_view(), name="flashcard_create"),
#     path("flashcard/update/<pk>", views.FlashCardUpdate.as_view(), name="flashcard_update"),
#     path("flashcard/delete/<pk>", views.FlashCardDelete.as_view(), name="flashcard_delete"),
#
#     path("quizhistory/list/", views.QuizHistoryList.as_view(), name="quiz_history_list"),
#     path("quizhistorylist/delete/<pk>", views.QuizHistoryDelete.as_view(), name="quiz_history_delete"),
#
#     path("account/", include("django.contrib.auth.urls")),
#     # path("logout/", views.logout_view, name="logout"),
#     path("signup/", views.SignUp.as_view(), name="signup"),
# ]