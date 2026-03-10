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
