from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .models import NoteAttempt, NoteStats, PositionStats, UserProfile
import json
import random

# ─── Fretboard Data ───
ALL_NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
ENHARMONIC = {
    'C#': 'Db', 'D#': 'Eb', 'F#': 'Gb', 'G#': 'Ab', 'A#': 'Bb',
    'Db': 'C#', 'Eb': 'D#', 'Gb': 'F#', 'Ab': 'G#', 'Bb': 'A#',
}
# Standard tuning (string 1 = high E to string 6 = low E)
OPEN_STRINGS = {
    1: 'E',  # high E
    2: 'B',
    3: 'G',
    4: 'D',
    5: 'A',
    6: 'E',  # low E
}

# Natural notes (no sharps/flats)
NATURAL_NOTES = ['C', 'D', 'E', 'F', 'G', 'A', 'B']

# Sharp notes
SHARP_NOTES = ['C#', 'D#', 'F#', 'G#', 'A#']

# Flat notes
FLAT_NOTES = ['Db', 'Eb', 'Gb', 'Ab', 'Bb']


def get_note_at_position(string_num, fret_num):
    """Return the note name at a given string and fret."""
    open_note = OPEN_STRINGS[string_num]
    open_index = ALL_NOTES.index(open_note)
    note_index = (open_index + fret_num) % 12
    return ALL_NOTES[note_index]


def get_all_positions_for_note(note, fret_range=None):
    """Get all (string, fret) positions where a note can be found."""
    # Handle enharmonic equivalents
    search_notes = [note]
    if note in ENHARMONIC:
        search_notes.append(ENHARMONIC[note])

    positions = []
    for s in range(1, 7):
        for f in range(0, 13):
            if fret_range and f not in fret_range:
                continue
            n = get_note_at_position(s, f)
            if n in search_notes or n == note:
                positions.append((s, f))
    return positions


def build_fretboard_data():
    """Build complete fretboard note map."""
    fretboard = {}
    for s in range(1, 7):
        for f in range(0, 13):
            note = get_note_at_position(s, f)
            fretboard[f"{s}-{f}"] = note
    return fretboard


# ─── Views ───

def home(request):
    """Landing page."""
    context = {
        'fretboard': json.dumps(build_fretboard_data()),
    }
    if request.user.is_authenticated:
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        stats = NoteStats.objects.filter(user=request.user)
        total_attempts = sum(s.total_attempts for s in stats)
        total_correct = sum(s.correct_attempts for s in stats)
        context['profile'] = profile
        context['total_attempts'] = total_attempts
        context['total_correct'] = total_correct
        context['accuracy'] = round(total_correct / total_attempts * 100, 1) if total_attempts > 0 else 0
    return render(request, 'trainer/home.html', context)


def signup(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            UserProfile.objects.create(user=user)
            login(request, user)
            return redirect('home')
    else:
        form = UserCreationForm()
    return render(request, 'trainer/signup.html', {'form': form})


def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('home')
        else:
            return render(request, 'trainer/login.html', {'error': 'Invalid credentials'})
    return render(request, 'trainer/login.html')


def logout_view(request):
    logout(request)
    return redirect('home')


def game_identify(request):
    """Note identification game: a position is highlighted, user guesses the note."""
    context = {
        'fretboard': json.dumps(build_fretboard_data()),
        'all_notes': json.dumps(ALL_NOTES),
        'enharmonic': json.dumps(ENHARMONIC),
        'natural_notes': json.dumps(NATURAL_NOTES),
        'sharp_notes': json.dumps(SHARP_NOTES),
        'flat_notes': json.dumps(FLAT_NOTES),
    }

    if request.user.is_authenticated:
        stats = list(NoteStats.objects.filter(user=request.user).values('note', 'total_attempts', 'correct_attempts', 'streak'))
        context['user_stats'] = json.dumps(stats)
    else:
        context['user_stats'] = json.dumps([])

    return render(request, 'trainer/game_identify.html', context)


def game_find(request):
    """Find-the-note game: user is told to find a note in a region, clicks correct position."""
    context = {
        'fretboard': json.dumps(build_fretboard_data()),
        'all_notes': json.dumps(ALL_NOTES),
        'enharmonic': json.dumps(ENHARMONIC),
        'natural_notes': json.dumps(NATURAL_NOTES),
        'sharp_notes': json.dumps(SHARP_NOTES),
        'flat_notes': json.dumps(FLAT_NOTES),
    }

    if request.user.is_authenticated:
        stats = list(NoteStats.objects.filter(user=request.user).values('note', 'total_attempts', 'correct_attempts', 'streak'))
        context['user_stats'] = json.dumps(stats)
    else:
        context['user_stats'] = json.dumps([])

    return render(request, 'trainer/game_find.html', context)


def tuner_view(request):
    """Standalone tuner / string-walk exercise."""
    context = {
        'fretboard': json.dumps(build_fretboard_data()),
    }
    return render(request, 'trainer/tuner.html', context)


@login_required
def stats_view(request):
    """View user's progress stats."""
    note_stats = NoteStats.objects.filter(user=request.user).order_by('note')
    position_stats = PositionStats.objects.filter(user=request.user)
    recent_attempts = NoteAttempt.objects.filter(user=request.user)[:50]

    # Build heatmap data
    heatmap = {}
    for ps in position_stats:
        heatmap[f"{ps.string_number}-{ps.fret_number}"] = {
            'accuracy': round(ps.accuracy * 100, 1),
            'attempts': ps.total_attempts,
        }

    total_attempts = sum(s.total_attempts for s in note_stats)
    total_correct = sum(s.correct_attempts for s in note_stats)

    context = {
        'note_stats': note_stats,
        'heatmap': json.dumps(heatmap),
        'recent_attempts': recent_attempts,
        'total_attempts': total_attempts,
        'total_correct': total_correct,
        'accuracy': round(total_correct / total_attempts * 100, 1) if total_attempts > 0 else 0,
        'fretboard': json.dumps(build_fretboard_data()),
    }
    return render(request, 'trainer/stats.html', context)


# ─── API Endpoints ───

@require_POST
def api_record_attempt(request):
    """Record a game attempt and return updated stats."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    note = data.get('note', '')
    string_num = data.get('string')
    fret_num = data.get('fret')
    correct = data.get('correct', False)
    game_mode = data.get('game_mode', 'identify')

    if not request.user.is_authenticated:
        # Still return success for anonymous users, just don't store
        return JsonResponse({'stored': False, 'message': 'Login to save progress'})

    # Record the attempt
    NoteAttempt.objects.create(
        user=request.user,
        note=note,
        string_number=string_num,
        fret_number=fret_num,
        correct=correct,
        game_mode=game_mode,
    )

    # Update note stats
    note_stat, _ = NoteStats.objects.get_or_create(user=request.user, note=note)
    note_stat.total_attempts += 1
    if correct:
        note_stat.correct_attempts += 1
        note_stat.streak += 1
    else:
        note_stat.streak = 0
    note_stat.save()

    # Update position stats
    pos_stat, _ = PositionStats.objects.get_or_create(
        user=request.user, string_number=string_num, fret_number=fret_num
    )
    pos_stat.total_attempts += 1
    if correct:
        pos_stat.correct_attempts += 1
    pos_stat.save()

    return JsonResponse({
        'stored': True,
        'note_accuracy': round(note_stat.accuracy * 100, 1),
        'note_streak': note_stat.streak,
        'note_total': note_stat.total_attempts,
    })


def api_get_weighted_note(request):
    """Get a weighted random note based on user's history."""
    filter_param = request.GET.get('filter', 'all')

    # Determine which notes to pick from
    if filter_param == 'all':
        available_notes = ALL_NOTES[:]
    elif filter_param == 'naturals':
        available_notes = NATURAL_NOTES[:]
    elif filter_param == 'sharps':
        available_notes = SHARP_NOTES[:]
    elif filter_param == 'flats':
        available_notes = FLAT_NOTES[:]
    else:
        # Custom filter - comma separated
        try:
            available_notes = json.loads(filter_param)
        except (json.JSONDecodeError, TypeError):
            available_notes = ALL_NOTES[:]

    if not available_notes:
        available_notes = ALL_NOTES[:]

    if request.user.is_authenticated:
        stats = {s.note: s for s in NoteStats.objects.filter(user=request.user, note__in=available_notes)}
        weights = []
        for note in available_notes:
            if note in stats:
                weights.append(stats[note].weight)
            else:
                weights.append(5.0)  # Default weight for untried notes
    else:
        weights = [1.0] * len(available_notes)

    # Weighted random selection
    chosen_note = random.choices(available_notes, weights=weights, k=1)[0]

    # Pick a random position for this note
    positions = get_all_positions_for_note(chosen_note)
    if positions:
        string_num, fret_num = random.choice(positions)
    else:
        string_num, fret_num = 1, 0

    return JsonResponse({
        'note': chosen_note,
        'string': string_num,
        'fret': fret_num,
        'enharmonic': ENHARMONIC.get(chosen_note, None),
    })


def api_get_find_challenge(request):
    """Get a challenge: find a specific note in a region of the fretboard."""
    filter_param = request.GET.get('filter', 'all')
    region = request.GET.get('region', 'all')  # e.g. '0-4', '5-8', '9-12', 'all'

    # Determine notes
    if filter_param == 'all':
        available_notes = ALL_NOTES[:]
    elif filter_param == 'naturals':
        available_notes = NATURAL_NOTES[:]
    elif filter_param == 'sharps':
        available_notes = SHARP_NOTES[:]
    elif filter_param == 'flats':
        available_notes = FLAT_NOTES[:]
    else:
        try:
            available_notes = json.loads(filter_param)
        except (json.JSONDecodeError, TypeError):
            available_notes = ALL_NOTES[:]

    if not available_notes:
        available_notes = ALL_NOTES[:]

    # Determine fret range
    if region == 'all':
        fret_range = list(range(0, 13))
    else:
        try:
            parts = region.split('-')
            fret_range = list(range(int(parts[0]), int(parts[1]) + 1))
        except (ValueError, IndexError):
            fret_range = list(range(0, 13))

    # Weighted selection
    if request.user.is_authenticated:
        stats = {s.note: s for s in NoteStats.objects.filter(user=request.user, note__in=available_notes)}
        weights = []
        for note in available_notes:
            if note in stats:
                weights.append(stats[note].weight)
            else:
                weights.append(5.0)
    else:
        weights = [1.0] * len(available_notes)

    chosen_note = random.choices(available_notes, weights=weights, k=1)[0]

    # Get valid positions in the region
    positions = get_all_positions_for_note(chosen_note, fret_range=fret_range)

    return JsonResponse({
        'note': chosen_note,
        'enharmonic': ENHARMONIC.get(chosen_note, None),
        'valid_positions': [{'string': s, 'fret': f} for s, f in positions],
        'region': region,
    })


def api_get_stats(request):
    """Return user stats as JSON."""
    if not request.user.is_authenticated:
        return JsonResponse({'authenticated': False})

    note_stats = NoteStats.objects.filter(user=request.user)
    stats_data = []
    for s in note_stats:
        stats_data.append({
            'note': s.note,
            'total': s.total_attempts,
            'correct': s.correct_attempts,
            'accuracy': round(s.accuracy * 100, 1),
            'streak': s.streak,
            'weight': round(s.weight, 2),
        })

    return JsonResponse({
        'authenticated': True,
        'stats': stats_data,
    })
