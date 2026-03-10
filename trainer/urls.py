from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('signup/', views.signup, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('game/identify/', views.game_identify, name='game_identify'),
    path('game/find/', views.game_find, name='game_find'),
    path('stats/', views.stats_view, name='stats'),
    path('leaderboard/', views.leaderboard_view, name='leaderboard'),
    path('tuner/', views.tuner_view, name='tuner'),
    path('fullscreen/', views.fullscreen_view, name='fullscreen'),

    # API
    path('api/record-attempt/', views.api_record_attempt, name='api_record_attempt'),
    path('api/weighted-note/', views.api_get_weighted_note, name='api_weighted_note'),
    path('api/find-challenge/', views.api_get_find_challenge, name='api_find_challenge'),
    path('api/stats/', views.api_get_stats, name='api_stats'),
    path('api/step-progress/', views.api_update_step_progress, name='api_step_progress'),
    path('api/record-streak/', views.api_record_streak, name='api_record_streak'),
]
