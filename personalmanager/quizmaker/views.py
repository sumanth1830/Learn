from django.shortcuts import render, redirect
from django.http import  HttpResponse, Http404
from django.template import loader
from .models import Quiz, QuizHistory, FlashCard
from django.views.generic.edit import UpdateView, DeleteView, CreateView
from django.views.generic import ListView
from .forms import FlashCardForm
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.urls import reverse_lazy
# Create your views here.

def home(request):
    template = loader.get_template("quizmaker/home.html")
    # return redirect("Welcome to the Quiz Maker!")
    return render(request, "quizmaker/home.html")


def login_view(request):
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            # send them wherever makes sense post-login — home shown here
            return redirect("quiz:home")
    else:
        form = AuthenticationForm(request)

    return render(request, "login.html", {"form": form})


def logout_view(request):
    logout(request)
    return redirect("quiz:home")

class SignUp(CreateView):
    form_class = UserCreationForm
    # reverse lazy generates a full url from a name
    success_url = reverse_lazy("login")
    template_name = "registration/signup.html"

class FlashCardList(LoginRequiredMixin, ListView):
    model = FlashCard
    template_name = "quizmaker/flashcard_list.html"

class FlashCardCreate(LoginRequiredMixin, CreateView):
    model = FlashCard
    fields = ["front_text", "hint", "explanation", "topic"]
    template_name = "quizmaker/flashcard_form.html"
    form_class = FlashCardForm

class FlashCardUpdate(LoginRequiredMixin, UpdateView):
    model = FlashCard
    fields = ["front_text", "hint", "explanation", "topic"]
    template_name = "quizmaker/flashcard_form.html"

class FlashCardDelete(LoginRequiredMixin, DeleteView):
    model = FlashCard
    template_name = "quizmaker/flashcard_confirm_delete.html"

class QuizHistoryList(LoginRequiredMixin, ListView):
    model = QuizHistory
    template_name = "quizmaker/quizhistory_list.html"

class QuizHistoryDelete(LoginRequiredMixin, DeleteView):
    model = QuizHistory
    template_name = "quizmaker/flashcard_confirm_delete.html"