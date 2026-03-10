from django.contrib import admin
from .models import NoteAttempt, NoteStats, PositionStats, UserProfile, PracticeStepProgress, DailyPracticeLog


@admin.register(NoteAttempt)
class NoteAttemptAdmin(admin.ModelAdmin):
    list_display = ('user', 'note', 'string_number', 'fret_number', 'correct', 'game_mode', 'timestamp')
    list_filter = ('correct', 'game_mode', 'note')
    search_fields = ('user__username',)


@admin.register(NoteStats)
class NoteStatsAdmin(admin.ModelAdmin):
    list_display = ('user', 'note', 'total_attempts', 'correct_attempts', 'streak')
    list_filter = ('note',)


@admin.register(PositionStats)
class PositionStatsAdmin(admin.ModelAdmin):
    list_display = ('user', 'string_number', 'fret_number', 'total_attempts', 'correct_attempts')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'total_games_played')


@admin.register(PracticeStepProgress)
class PracticeStepProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'current_step', 'step1_current_note', 'step1_current_streak')


@admin.register(DailyPracticeLog)
class DailyPracticeLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'date', 'exercises_completed', 'total_minutes')
    list_filter = ('date',)
