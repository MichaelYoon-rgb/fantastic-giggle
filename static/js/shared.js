/* ═══════════════════════════════════════════════════════════
   FRETBOARD TRAINER — Shared Utilities
   Note colors, sound synthesis, and microphone pitch detection
   ═══════════════════════════════════════════════════════════ */

// ─── NOTE COLORS (Change these to customize!) ───
// Each note gets its own PASTEL color. Edit the hex values below.
const NOTE_COLORS = {
    'C':  '#f4a5b0',  // Pastel Pink
    'C#': '#f8c4a4',  // Pastel Peach
    'Db': '#f8c4a4',  // Pastel Peach (enharmonic of C#)
    'D':  '#f7e5a0',  // Pastel Yellow
    'D#': '#d4e8a0',  // Pastel Lime
    'Eb': '#d4e8a0',  // Pastel Lime (enharmonic of D#)
    'E':  '#a8e6cf',  // Pastel Mint
    'F':  '#8dd9b8',  // Pastel Green
    'F#': '#90d8e8',  // Pastel Aqua
    'Gb': '#90d8e8',  // Pastel Aqua (enharmonic of F#)
    'G':  '#a0d2f0',  // Pastel Sky
    'G#': '#b0baf0',  // Pastel Periwinkle
    'Ab': '#b0baf0',  // Pastel Periwinkle (enharmonic of G#)
    'A':  '#c4b0e8',  // Pastel Lavender
    'A#': '#d4a5d8',  // Pastel Lilac
    'Bb': '#d4a5d8',  // Pastel Lilac (enharmonic of A#)
    'B':  '#f0a5c4',  // Pastel Rose
};

function getNoteColor(note) {
    // Handle enharmonic names like 'C#/Db'
    if (note && note.includes('/')) {
        const parts = note.split('/');
        return NOTE_COLORS[parts[0]] || NOTE_COLORS[parts[1]] || '#c4b0e8';
    }
    return NOTE_COLORS[note] || '#c4b0e8';
}

// ─── NOTE FREQUENCIES (Hz) for sound playback ───
// Standard tuning, octave 4 as base
const NOTE_FREQ_BASE = {
    'C': 261.63, 'C#': 277.18, 'D': 293.66, 'D#': 311.13,
    'E': 329.63, 'F': 349.23, 'F#': 369.99, 'G': 392.00,
    'G#': 415.30, 'A': 440.00, 'A#': 466.16, 'B': 493.88,
};

// Guitar string open frequencies (standard tuning)
const STRING_FREQUENCIES = {
    6: 82.41,   // Low E2
    5: 110.00,  // A2
    4: 146.83,  // D3
    3: 196.00,  // G3
    2: 246.94,  // B3
    1: 329.63,  // High E4
};

let audioCtx = null;

function getAudioContext() {
    if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    return audioCtx;
}

/**
 * Play a note sound using Web Audio API — Karplus-Strong inspired acoustic guitar
 * @param {string} note - Note name (e.g. 'A', 'C#')
 * @param {number} stringNum - String number (1-6) for octave calculation
 * @param {number} fretNum - Fret number (0-12)
 * @param {number} duration - Duration in seconds
 */
function playNoteSound(note, stringNum, fretNum, duration = 1.5) {
    try {
        const ctx = getAudioContext();
        const now = ctx.currentTime;

        // Calculate actual frequency based on string and fret
        const openFreq = STRING_FREQUENCIES[stringNum] || 329.63;
        const freq = openFreq * Math.pow(2, fretNum / 12);

        // --- Karplus-Strong style plucked string ---
        const sampleRate = ctx.sampleRate;
        const periodSamples = Math.round(sampleRate / freq);
        const bufferLength = Math.round(sampleRate * duration);
        const buffer = ctx.createBuffer(1, bufferLength, sampleRate);
        const data = buffer.getChannelData(0);

        // Seed the delay line with filtered noise burst (simulates the pluck)
        for (let i = 0; i < periodSamples; i++) {
            data[i] = (Math.random() * 2 - 1) * 0.6;
        }

        // Apply a short averaging filter to the initial burst for body warmth
        // Lower strings get more filtering (warmer), higher strings stay brighter
        const burstSmooth = stringNum >= 4 ? 3 : stringNum >= 2 ? 2 : 1;
        for (let pass = 0; pass < burstSmooth; pass++) {
            for (let i = 1; i < periodSamples; i++) {
                data[i] = data[i] * 0.5 + data[i - 1] * 0.5;
            }
        }

        // Feedback loop: each new sample = average of sample one period ago + neighbour, with decay
        const decay = 0.996 + (stringNum - 1) * 0.0005; // thicker strings ring longer
        for (let i = periodSamples; i < bufferLength; i++) {
            data[i] = (data[i - periodSamples] + data[i - periodSamples + 1]) * 0.5 * decay;
        }

        // Play the buffer
        const src = ctx.createBufferSource();
        src.buffer = buffer;

        // Body resonance filter (simulates guitar body)
        const bodyFilter = ctx.createBiquadFilter();
        bodyFilter.type = 'peaking';
        bodyFilter.frequency.value = 250; // guitar body resonance ~250Hz
        bodyFilter.Q.value = 2.5;
        bodyFilter.gain.value = 4;

        // Brightness filter — roll off harsh highs
        const brightnessFilter = ctx.createBiquadFilter();
        brightnessFilter.type = 'lowpass';
        brightnessFilter.frequency.value = 4000 - (stringNum - 1) * 400; // bass strings darker
        brightnessFilter.Q.value = 0.7;

        // Gain envelope
        const gainNode = ctx.createGain();
        gainNode.gain.setValueAtTime(0.35, now);
        gainNode.gain.exponentialRampToValueAtTime(0.001, now + duration);

        // Connect chain: src → body → brightness → gain → output
        src.connect(bodyFilter);
        bodyFilter.connect(brightnessFilter);
        brightnessFilter.connect(gainNode);
        gainNode.connect(ctx.destination);

        src.start(now);
        src.stop(now + duration);
    } catch (e) {
        console.log('Audio playback error:', e);
    }
}

// ─── MICROPHONE PITCH DETECTION ───

class PitchDetector {
    constructor() {
        this.audioContext = null;
        this.analyser = null;
        this.stream = null;
        this.isListening = false;
        this.onNoteDetected = null;
        this.bufferSize = 4096;
        this.buffer = new Float32Array(this.bufferSize);
        this.detectionInterval = null;
        this.lastDetectedNote = null;
        this.lastDetectedTime = 0;
        this.confidenceThreshold = 0.9;
    }

    async start() {
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: false,
                    noiseSuppression: false,
                    autoGainControl: false,
                }
            });

            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const source = this.audioContext.createMediaStreamSource(this.stream);

            this.analyser = this.audioContext.createAnalyser();
            this.analyser.fftSize = this.bufferSize * 2;
            this.analyser.smoothingTimeConstant = 0.8;

            source.connect(this.analyser);
            this.isListening = true;

            // Start detection loop
            this.detectionInterval = setInterval(() => this.detect(), 50);
            return true;
        } catch (e) {
            console.error('Microphone access denied:', e);
            return false;
        }
    }

    stop() {
        this.isListening = false;
        if (this.detectionInterval) {
            clearInterval(this.detectionInterval);
            this.detectionInterval = null;
        }
        if (this.stream) {
            this.stream.getTracks().forEach(t => t.stop());
            this.stream = null;
        }
        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }
    }

    detect() {
        if (!this.isListening || !this.analyser) return;

        this.analyser.getFloatTimeDomainData(this.buffer);

        // Check if there's enough signal (volume gate)
        let rms = 0;
        for (let i = 0; i < this.buffer.length; i++) {
            rms += this.buffer[i] * this.buffer[i];
        }
        rms = Math.sqrt(rms / this.buffer.length);

        if (rms < 0.01) return; // Too quiet, skip

        // Autocorrelation pitch detection
        const freq = this.autoCorrelate(this.buffer, this.audioContext.sampleRate);

        if (freq > 0) {
            const noteInfo = this.frequencyToNote(freq);
            const now = Date.now();

            // Debounce: only fire if it's a new note or 300ms has passed
            if (noteInfo.note !== this.lastDetectedNote || now - this.lastDetectedTime > 300) {
                this.lastDetectedNote = noteInfo.note;
                this.lastDetectedTime = now;

                if (this.onNoteDetected) {
                    this.onNoteDetected(noteInfo);
                }
            }
        }
    }

    autoCorrelate(buf, sampleRate) {
        // Find a good enough correlation
        let SIZE = buf.length;
        let MAX_SAMPLES = Math.floor(SIZE / 2);
        let best_offset = -1;
        let best_correlation = 0;
        let foundGoodCorrelation = false;
        let correlations = new Array(MAX_SAMPLES);

        // Trim silence from edges
        let start = 0, end = SIZE - 1;
        const thresh = 0.2;
        for (let i = 0; i < SIZE / 2; i++) {
            if (Math.abs(buf[i]) > thresh) { start = i; break; }
        }
        for (let i = SIZE - 1; i >= SIZE / 2; i--) {
            if (Math.abs(buf[i]) > thresh) { end = i; break; }
        }

        buf = buf.slice(start, end);
        SIZE = buf.length;
        MAX_SAMPLES = Math.floor(SIZE / 2);

        if (SIZE < 100) return -1;

        for (let offset = 8; offset < MAX_SAMPLES; offset++) {
            let correlation = 0;
            for (let i = 0; i < MAX_SAMPLES; i++) {
                correlation += Math.abs((buf[i]) - (buf[i + offset]));
            }
            correlation = 1 - (correlation / MAX_SAMPLES);
            correlations[offset] = correlation;

            if (correlation > this.confidenceThreshold && correlation > best_correlation) {
                best_correlation = correlation;
                best_offset = offset;
                foundGoodCorrelation = true;
            } else if (foundGoodCorrelation) {
                // We found a peak, now going down — we're done
                break;
            }
        }

        if (best_correlation > this.confidenceThreshold) {
            // Refine with parabolic interpolation
            let shift = 0;
            if (best_offset > 0 && best_offset < MAX_SAMPLES - 1) {
                const prev = correlations[best_offset - 1] || 0;
                const curr = correlations[best_offset];
                const next = correlations[best_offset + 1] || 0;
                shift = (next - prev) / (2 * (2 * curr - next - prev));
            }
            return sampleRate / (best_offset + shift);
        }
        return -1;
    }

    frequencyToNote(freq) {
        // Get the note and octave from frequency
        const noteNames = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
        const noteNum = 12 * (Math.log2(freq / 440)) + 69;
        const roundedNote = Math.round(noteNum);
        const noteIndex = ((roundedNote % 12) + 12) % 12;
        const octave = Math.floor(roundedNote / 12) - 1;
        const centsOff = Math.round(1200 * Math.log2(freq / (440 * Math.pow(2, (roundedNote - 69) / 12))));

        return {
            note: noteNames[noteIndex],
            octave: octave,
            frequency: freq,
            cents: centsOff,
            midi: roundedNote,
        };
    }

    /**
     * Given a detected frequency, guess which (string, fret) the user played
     */
    guessPosition(freq) {
        const noteInfo = this.frequencyToNote(freq);
        const midi = noteInfo.midi;

        // MIDI notes for open strings (standard tuning)
        const openStringMidi = {
            6: 40, // E2
            5: 45, // A2
            4: 50, // D3
            3: 55, // G3
            2: 59, // B3
            1: 64, // E4
        };

        let bestString = null;
        let bestFret = null;
        let bestDistance = Infinity;

        for (let s = 1; s <= 6; s++) {
            const fret = midi - openStringMidi[s];
            if (fret >= 0 && fret <= 12) {
                // Prefer lower positions as more likely
                const distance = fret;
                if (distance < bestDistance) {
                    bestDistance = distance;
                    bestString = s;
                    bestFret = fret;
                }
            }
        }

        return {
            string: bestString,
            fret: bestFret,
            note: noteInfo.note,
            octave: noteInfo.octave,
            frequency: freq,
        };
    }
}

// ─── FLOATING MUSIC NOTES BACKGROUND ───

function initFloatingNotes() {
    const canvas = document.getElementById('bgCanvas');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    let particles = [];
    const symbols = ['♪', '♫', '♬', '♩', '𝄞', '🎵', '🎶', '🎸', '🎤'];
    // Pastel colors for particles
    const pastelColors = [
        '#f4a5b0', '#c4b0e8', '#a8e6cf', '#f8c4a4',
        '#a0d2f0', '#f7e5a0', '#f09090', '#d4a5d8'
    ];
    const maxParticles = 20;

    function resize() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }

    window.addEventListener('resize', resize);
    resize();

    class Particle {
        constructor() {
            this.reset();
        }

        reset() {
            this.x = Math.random() * canvas.width;
            this.y = canvas.height + 20;
            this.size = 12 + Math.random() * 24;
            this.speedY = -(0.3 + Math.random() * 0.7);
            this.speedX = (Math.random() - 0.5) * 0.5;
            this.opacity = 0.04 + Math.random() * 0.08;
            this.symbol = symbols[Math.floor(Math.random() * symbols.length)];
            this.color = pastelColors[Math.floor(Math.random() * pastelColors.length)];
            this.rotation = Math.random() * Math.PI * 2;
            this.rotSpeed = (Math.random() - 0.5) * 0.02;
            this.wobblePhase = Math.random() * Math.PI * 2;
            this.wobbleSpeed = 0.01 + Math.random() * 0.02;
            this.wobbleAmp = 20 + Math.random() * 30;
        }

        update() {
            this.y += this.speedY;
            this.wobblePhase += this.wobbleSpeed;
            this.x += Math.sin(this.wobblePhase) * 0.5;
            this.rotation += this.rotSpeed;

            if (this.y < -40) {
                this.reset();
            }
        }

        draw() {
            ctx.save();
            ctx.translate(this.x, this.y);
            ctx.rotate(this.rotation);
            ctx.globalAlpha = this.opacity;
            ctx.fillStyle = this.color;
            ctx.font = `${this.size}px serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(this.symbol, 0, 0);
            ctx.restore();
        }
    }

    // Initialize particles
    for (let i = 0; i < maxParticles; i++) {
        const p = new Particle();
        p.y = Math.random() * canvas.height; // Spread initially
        particles.push(p);
    }

    function animate() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        particles.forEach(p => {
            p.update();
            p.draw();
        });
        requestAnimationFrame(animate);
    }

    animate();
}

// ─── SOUND WAVE BACKGROUND ANIMATION ───

function initSoundWaves() {
    const canvas = document.getElementById('waveCanvas');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    let time = 0;

    function resize() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }

    window.addEventListener('resize', resize);
    resize();

    function animate() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        time += 0.008;

        // Draw multiple sine waves with pastel colors
        const waves = [
            { amplitude: 30, frequency: 0.004, speed: 0.8, color: 'rgba(244, 165, 176, 0.04)', yOffset: 0.25 },
            { amplitude: 40, frequency: 0.007, speed: 0.5, color: 'rgba(196, 176, 232, 0.035)', yOffset: 0.45 },
            { amplitude: 25, frequency: 0.010, speed: 1.0, color: 'rgba(168, 230, 207, 0.035)', yOffset: 0.65 },
            { amplitude: 35, frequency: 0.005, speed: 0.7, color: 'rgba(248, 196, 164, 0.03)', yOffset: 0.35 },
            { amplitude: 22, frequency: 0.013, speed: 0.9, color: 'rgba(160, 210, 240, 0.035)', yOffset: 0.55 },
            { amplitude: 18, frequency: 0.016, speed: 1.2, color: 'rgba(247, 229, 160, 0.025)', yOffset: 0.8 },
        ];

        waves.forEach(wave => {
            ctx.beginPath();
            ctx.strokeStyle = wave.color;
            ctx.lineWidth = 2;

            const y0 = canvas.height * wave.yOffset;

            for (let x = 0; x < canvas.width; x += 2) {
                const y = y0 +
                    Math.sin(x * wave.frequency + time * wave.speed) * wave.amplitude +
                    Math.sin(x * wave.frequency * 2.3 + time * wave.speed * 1.5) * wave.amplitude * 0.3;

                if (x === 0) {
                    ctx.moveTo(x, y);
                } else {
                    ctx.lineTo(x, y);
                }
            }
            ctx.stroke();
        });

        requestAnimationFrame(animate);
    }

    animate();
}

// Init backgrounds on load
document.addEventListener('DOMContentLoaded', () => {
    initFloatingNotes();
    initSoundWaves();
});
