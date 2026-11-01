from django.shortcuts import render


def game_test_view(request):
    return render(request, "quizmaker/game_test.html")