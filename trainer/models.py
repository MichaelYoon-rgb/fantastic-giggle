from django.db import models
from django.contrib.auth.models import User
import json


class NoteAttempt(models.Model):
    """Tracks each individual attempt at identifying a note."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='note_attempts')
    note = models.CharField(max_length=3)  # e.g. 'A', 'A#', 'Bb'
    string_number = models.IntegerField()  # 1-6 (1=high E, 6=low E)
    fret_number = models.IntegerField()  # 0-12
    correct = models.BooleanField()
    game_mode = models.CharField(max_length=20, choices=[
        ('identify', 'Identify Note'),
        ('find', 'Find Note'),
    ])
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        result = "✓" if self.correct else "✗"
        return f"{result} {self.note} (string {self.string_number}, fret {self.fret_number})"


class NoteStats(models.Model):
    """Aggregated stats per note per user for adaptive difficulty."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='note_stats')
    note = models.CharField(max_length=3)
    total_attempts = models.IntegerField(default=0)
    correct_attempts = models.IntegerField(default=0)
    streak = models.IntegerField(default=0)  # current correct streak
    last_attempted = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'note')
        ordering = ['note']

    @property
    def accuracy(self):
        if self.total_attempts == 0:
            return 0.0
        return self.correct_attempts / self.total_attempts

    @property
    def accuracy_pct(self):
        return round(self.accuracy * 100, 1)

    @property
    def weight(self):
        """Higher weight = more likely to appear. Bad notes get higher weight."""
        if self.total_attempts == 0:
            return 5.0  # Medium weight for untried notes
        error_rate = 1.0 - self.accuracy
        # Base weight from error rate (0-10 scale)
        base_weight = 1.0 + (error_rate * 9.0)
        # Bonus for low attempt count (encourage trying all notes)
        attempt_bonus = max(0, 3.0 - (self.total_attempts / 10.0))
        return base_weight + attempt_bonus

    def __str__(self):
        return f"{self.note}: {self.correct_attempts}/{self.total_attempts}"


class PositionStats(models.Model):
    """Aggregated stats per string+fret position per user."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='position_stats')
    string_number = models.IntegerField()
    fret_number = models.IntegerField()
    total_attempts = models.IntegerField(default=0)
    correct_attempts = models.IntegerField(default=0)

    class Meta:
        unique_together = ('user', 'string_number', 'fret_number')

    @property
    def accuracy(self):
        if self.total_attempts == 0:
            return 0.0
        return self.correct_attempts / self.total_attempts

    @property
    def weight(self):
        if self.total_attempts == 0:
            return 5.0
        error_rate = 1.0 - self.accuracy
        return 1.0 + (error_rate * 9.0)

    def __str__(self):
        return f"String {self.string_number}, Fret {self.fret_number}: {self.correct_attempts}/{self.total_attempts}"


class UserProfile(models.Model):
    """Extended user profile for preferences."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    total_games_played = models.IntegerField(default=0)
    preferred_filter = models.TextField(default='all')  # JSON list of notes or 'all'

    def get_filter_notes(self):
        if self.preferred_filter == 'all':
            return None
        try:
            return json.loads(self.preferred_filter)
        except (json.JSONDecodeError, TypeError):
            return None

    def set_filter_notes(self, notes):
        if notes is None:
            self.preferred_filter = 'all'
        else:
            self.preferred_filter = json.dumps(notes)

    def __str__(self):
        return f"Profile for {self.user.username}"


class PracticeStepProgress(models.Model):
    """Tracks the user's progress through the 6-step fretboard mastery pathway."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='step_progress')
    current_step = models.IntegerField(default=1)  # 1-6
    # Step 1: track which natural notes have been completed twice
    step1_note_completions = models.TextField(default='{}')  # JSON {note: count}
    step1_current_note = models.CharField(max_length=3, default='')
    step1_current_streak = models.IntegerField(default=0)  # 3 perfect runs needed
    # Step 2: same as step 1 but with metronome — track which notes done
    step2_notes_done = models.TextField(default='[]')  # JSON list
    # Step 3: sharps & flats done
    step3_notes_done = models.TextField(default='[]')
    # Step 4: pair practice
    step4_completed = models.BooleanField(default=False)
    # Step 5: random order mastered
    step5_completed = models.BooleanField(default=False)
    # Step 6: current BPM level
    step6_current_bpm = models.IntegerField(default=40)
    step6_completed = models.BooleanField(default=False)

    def get_step1_completions(self):
        try:
            return json.loads(self.step1_note_completions)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_step1_completions(self, data):
        self.step1_note_completions = json.dumps(data)

    def get_step2_notes(self):
        try:
            return json.loads(self.step2_notes_done)
        except (json.JSONDecodeError, TypeError):
            return []

    def get_step3_notes(self):
        try:
            return json.loads(self.step3_notes_done)
        except (json.JSONDecodeError, TypeError):
            return []

    def __str__(self):
        return f"{self.user.username} — Step {self.current_step}"


class DailyPracticeLog(models.Model):
    """Tracks which exercises were completed each day for the calendar."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='practice_logs')
    date = models.DateField()
    exercises_completed = models.TextField(default='[]')  # JSON list of exercise keys
    total_minutes = models.IntegerField(default=0)

    class Meta:
        unique_together = ('user', 'date')
        ordering = ['-date']

    def get_exercises(self):
        try:
            return json.loads(self.exercises_completed)
        except (json.JSONDecodeError, TypeError):
            return []

    def add_exercise(self, exercise_key):
        exercises = self.get_exercises()
        if exercise_key not in exercises:
            exercises.append(exercise_key)
            self.exercises_completed = json.dumps(exercises)
            self.save()

    @property
    def completion_ratio(self):
        """How full the circle should be (0.0 to 1.0)."""
        exercises = self.get_exercises()
        # 6 possible exercises (one per step, but only current step counts)
        return min(1.0, len(exercises) / 3.0)  # 3 exercises for a full day

    def __str__(self):
        return f"{self.user.username} — {self.date}"


class StreakRecord(models.Model):
    """Records best streaks for the global leaderboard."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='streak_records')
    streak = models.IntegerField()
    game_mode = models.CharField(max_length=20, choices=[
        ('identify', 'Identify Note'),
        ('find', 'Find Note'),
    ])
    achieved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-streak', '-achieved_at']

    def __str__(self):
        return f"{self.user.username}: {self.streak} streak ({self.game_mode})"
