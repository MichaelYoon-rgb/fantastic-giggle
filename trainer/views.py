from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .models import NoteAttempt, NoteStats, PositionStats, UserProfile, PracticeStepProgress, DailyPracticeLog, StreakRecord
import json
import random
from datetime import date, timedelta, datetime
import calendar as cal_module
from django.utils import timezone
from django.db.models import Max

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
    context = {}
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
    """Fretboard mastery pathway with spaced repetition calendar."""
    context = {
        'fretboard': json.dumps(build_fretboard_data()),
    }

    if request.user.is_authenticated:
        progress, _ = PracticeStepProgress.objects.get_or_create(user=request.user)
        context['progress'] = progress
        context['step1_completions'] = progress.get_step1_completions()
        context['step2_notes'] = progress.get_step2_notes()
        context['step3_notes'] = progress.get_step3_notes()

        # Calendar data for current month
        today = date.today()
        year, month = today.year, today.month
        first_day = date(year, month, 1)
        num_days = cal_module.monthrange(year, month)[1]
        logs = DailyPracticeLog.objects.filter(
            user=request.user, date__year=year, date__month=month
        )
        log_map = {log.date.day: log.get_exercises() for log in logs}

        cal_data = []
        for d in range(1, num_days + 1):
            exercises = log_map.get(d, [])
            cal_data.append({
                'day': d,
                'exercises': exercises,
                'count': len(exercises),
                'is_today': d == today.day,
                'is_future': d > today.day,
            })
        context['calendar'] = json.dumps(cal_data)
        context['month_name'] = today.strftime('%B %Y')
        context['first_weekday'] = first_day.weekday()  # 0=Mon

    return render(request, 'trainer/tuner.html', context)


def fullscreen_view(request):
    """Full screen fretboard reference."""
    context = {
        'fretboard': json.dumps(build_fretboard_data()),
    }
    return render(request, 'trainer/fullscreen.html', context)


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


def leaderboard_view(request):
    """Global leaderboard showing best streaks by day, month, year, and all-time."""
    now = timezone.now()
    today = now.date()

    # Helper to get top streaks in a queryset
    def top_streaks(qs, limit=15):
        # Get the best streak per user, then order by streak desc
        return list(
            qs.values('user__username')
            .annotate(best=Max('streak'))
            .order_by('-best')[:limit]
        )

    all_records = StreakRecord.objects.all()

    context = {
        'today_streaks': top_streaks(all_records.filter(achieved_at__date=today)),
        'month_streaks': top_streaks(all_records.filter(achieved_at__year=now.year, achieved_at__month=now.month)),
        'year_streaks': top_streaks(all_records.filter(achieved_at__year=now.year)),
        'alltime_streaks': top_streaks(all_records),
        'today_label': today.strftime('%B %d, %Y'),
        'month_label': today.strftime('%B %Y'),
        'year_label': str(today.year),
    }

    # Current user's personal best
    if request.user.is_authenticated:
        personal = all_records.filter(user=request.user).order_by('-streak').first()
        context['personal_best'] = personal.streak if personal else 0
    else:
        context['personal_best'] = 0

    return render(request, 'trainer/leaderboard.html', context)


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

    # Avoid repeating the same position — read prev from query param
    prev_string = request.GET.get('ps', '')
    prev_fret = request.GET.get('pf', '')

    # Weighted random selection
    chosen_note = random.choices(available_notes, weights=weights, k=1)[0]

    # Pick a random position for this note
    positions = get_all_positions_for_note(chosen_note)
    # Exclude fret 0 (open strings) so user practises fretting
    positions = [(s, f) for s, f in positions if f > 0]

    # Try to avoid same position as last time
    if prev_string and prev_fret and len(positions) > 1:
        try:
            ps, pf = int(prev_string), int(prev_fret)
            filtered = [(s, f) for s, f in positions if not (s == ps and f == pf)]
            if filtered:
                positions = filtered
        except ValueError:
            pass

    if positions:
        string_num, fret_num = random.choice(positions)
    else:
        string_num, fret_num = 1, 1

    return JsonResponse({
        'note': chosen_note,
        'string': string_num,
        'fret': fret_num,
        'enharmonic': ENHARMONIC.get(chosen_note, None),
    })


def api_get_find_challenge(request):
    """Get a challenge: find a specific note in a region of the fretboard.
    Supports 3x3 blocks (3 frets × 3 strings) with no duplicate notes."""
    filter_param = request.GET.get('filter', 'all')
    region = request.GET.get('region', 'all')  # e.g. '0-4', '5-8', '9-12', 'all'
    mode = request.GET.get('mode', 'block')  # 'block' (3x3) or 'full' (all frets)

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

    if mode == 'full':
        # Full fretboard mode — find ALL instances of a note
        if request.user.is_authenticated:
            stats = {s.note: s for s in NoteStats.objects.filter(user=request.user, note__in=available_notes)}
            weights = [stats[n].weight if n in stats else 5.0 for n in available_notes]
        else:
            weights = [1.0] * len(available_notes)

        chosen_note = random.choices(available_notes, weights=weights, k=1)[0]
        positions = get_all_positions_for_note(chosen_note)

        return JsonResponse({
            'note': chosen_note,
            'enharmonic': ENHARMONIC.get(chosen_note, None),
            'valid_positions': [{'string': s, 'fret': f} for s, f in positions],
            'region': 'all',
            'mode': 'full',
            'block': None,
        })

    # Block mode — pick a random 3x3 block and ensure no duplicate notes
    max_attempts = 50
    for _ in range(max_attempts):
        # Random start fret (0-10 so we can have 3 frets: start, start+1, start+2)
        start_fret = random.randint(0, 10)
        fret_range = [start_fret, start_fret + 1, start_fret + 2]

        # Random start string (1-4 so we can have 3 strings: start, start+1, start+2)
        start_string = random.randint(1, 4)
        string_range = [start_string, start_string + 1, start_string + 2]

        # Collect notes in this block
        block_notes = set()
        has_duplicate = False
        for s in string_range:
            for f in fret_range:
                note = get_note_at_position(s, f)
                if note in block_notes:
                    has_duplicate = True
                    break
                block_notes.add(note)
            if has_duplicate:
                break

        if not has_duplicate:
            # Filter to only notes the user is practicing
            valid_block_notes = [n for n in block_notes if n in available_notes]
            if valid_block_notes:
                # Weighted selection from valid notes in this block
                if request.user.is_authenticated:
                    stats = {s.note: s for s in NoteStats.objects.filter(user=request.user, note__in=valid_block_notes)}
                    weights = [stats[n].weight if n in stats else 5.0 for n in valid_block_notes]
                else:
                    weights = [1.0] * len(valid_block_notes)

                chosen_note = random.choices(valid_block_notes, weights=weights, k=1)[0]

                # Get valid positions within this block
                positions = []
                for s in string_range:
                    for f in fret_range:
                        n = get_note_at_position(s, f)
                        if n == chosen_note or (chosen_note in ENHARMONIC and n == ENHARMONIC[chosen_note]):
                            positions.append((s, f))

                return JsonResponse({
                    'note': chosen_note,
                    'enharmonic': ENHARMONIC.get(chosen_note, None),
                    'valid_positions': [{'string': s, 'fret': f} for s, f in positions],
                    'region': f'{start_fret}-{start_fret + 2}',
                    'mode': 'block',
                    'block': {
                        'fret_start': start_fret,
                        'fret_end': start_fret + 2,
                        'string_start': start_string,
                        'string_end': start_string + 2,
                    },
                })

    # Fallback: if we couldn't find a no-duplicate block, just use any random block
    start_fret = random.randint(0, 10)
    start_string = random.randint(1, 4)
    fret_range = list(range(start_fret, start_fret + 3))
    string_range = list(range(start_string, start_string + 3))

    chosen_note = random.choice(available_notes)
    positions = []
    for s in string_range:
        for f in fret_range:
            n = get_note_at_position(s, f)
            if n == chosen_note or (chosen_note in ENHARMONIC and n == ENHARMONIC[chosen_note]):
                positions.append((s, f))

    return JsonResponse({
        'note': chosen_note,
        'enharmonic': ENHARMONIC.get(chosen_note, None),
        'valid_positions': [{'string': s, 'fret': f} for s, f in positions],
        'region': f'{start_fret}-{start_fret + 2}',
        'mode': 'block',
        'block': {
            'fret_start': start_fret,
            'fret_end': start_fret + 2,
            'string_start': start_string,
            'string_end': start_string + 2,
        },
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


@require_POST
def api_update_step_progress(request):
    """Update the user's step progress (complete exercise, advance step, etc.)."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Login required'}, status=401)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    action = data.get('action')
    progress, _ = PracticeStepProgress.objects.get_or_create(user=request.user)

    if action == 'complete_note_run':
        # Step 1: user completed a perfect run for a note
        note = data.get('note', '')
        completions = progress.get_step1_completions()
        progress.step1_current_note = note
        progress.step1_current_streak += 1

        if progress.step1_current_streak >= 3:
            # 3 perfect runs → count as 1 completion for this note
            completions[note] = completions.get(note, 0) + 1
            progress.set_step1_completions(completions)
            progress.step1_current_streak = 0
            progress.step1_current_note = ''

            # Check if all 7 naturals done twice
            naturals = ['C', 'D', 'E', 'F', 'G', 'A', 'B']
            all_done = all(completions.get(n, 0) >= 2 for n in naturals)
            if all_done and progress.current_step == 1:
                progress.current_step = 2

        progress.save()

    elif action == 'reset_note_streak':
        progress.step1_current_streak = 0
        progress.save()

    elif action == 'complete_step2_note':
        note = data.get('note', '')
        notes = progress.get_step2_notes()
        if note not in notes:
            notes.append(note)
            progress.step2_notes_done = json.dumps(notes)
        # All 7 naturals done → advance
        if len(notes) >= 7 and progress.current_step == 2:
            progress.current_step = 3
        progress.save()

    elif action == 'complete_step3_note':
        note = data.get('note', '')
        notes = progress.get_step3_notes()
        if note not in notes:
            notes.append(note)
            progress.step3_notes_done = json.dumps(notes)
        # All 5 sharps/flats done → advance
        if len(notes) >= 5 and progress.current_step == 3:
            progress.current_step = 4
        progress.save()

    elif action == 'complete_step4':
        progress.step4_completed = True
        if progress.current_step == 4:
            progress.current_step = 5
        progress.save()

    elif action == 'complete_step5':
        progress.step5_completed = True
        if progress.current_step == 5:
            progress.current_step = 6
        progress.save()

    elif action == 'update_step6_bpm':
        bpm = data.get('bpm', 40)
        progress.step6_current_bpm = bpm
        if bpm >= 80:
            progress.step6_completed = True
        progress.save()

    elif action == 'log_exercise':
        exercise_key = data.get('exercise', '')
        today = date.today()
        log, _ = DailyPracticeLog.objects.get_or_create(
            user=request.user, date=today
        )
        log.add_exercise(exercise_key)

    return JsonResponse({
        'current_step': progress.current_step,
        'step1_completions': progress.get_step1_completions(),
        'step1_streak': progress.step1_current_streak,
        'step1_note': progress.step1_current_note,
        'step2_notes': progress.get_step2_notes(),
        'step3_notes': progress.get_step3_notes(),
        'step4_completed': progress.step4_completed,
        'step5_completed': progress.step5_completed,
        'step6_bpm': progress.step6_current_bpm,
        'step6_completed': progress.step6_completed,
    })


@require_POST
def api_record_streak(request):
    """Record a streak to the leaderboard when it ends."""
    if not request.user.is_authenticated:
        return JsonResponse({'stored': False, 'message': 'Login to save streaks'})

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    streak_val = data.get('streak', 0)
    game_mode = data.get('game_mode', 'identify')

    if streak_val < 2:
        return JsonResponse({'stored': False, 'message': 'Streak too small'})

    StreakRecord.objects.create(
        user=request.user,
        streak=streak_val,
        game_mode=game_mode,
    )

    return JsonResponse({'stored': True, 'streak': streak_val})
