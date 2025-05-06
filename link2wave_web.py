import subprocess, threading, tempfile, json, sys, shlex, hashlib, shutil, pathlib, os
from flask import Flask, render_template_string, request, redirect, url_for, flash, Response, jsonify, send_file, render_template
# === Runtime deps ===
try:
    import torch, simpleaudio as sa, yt_dlp, demucs.separate   # noqa
    import numpy as np
    # Add sounddevice for pitch processing
    try:
        import sounddevice as sd
        import soundfile as sf
        import librosa
    except ImportError:
        print("Warning: sounddevice, soundfile, or librosa not installed. Pitch processing will not be available.")
except ImportError as boom:
    sys.exit(f"Missing lib: {boom}. Activate venv & pip install deps first.")

DEST_DIR = pathlib.Path.home() / "Music" / "YT-Rips"; DEST_DIR.mkdir(parents=True, exist_ok=True)
LAST_RIP = None; FFMPEG_OPTS = "-hide_banner -loglevel error"
PROCESSING = False
CURRENT_STEMS = {}

app = Flask(__name__)
app.secret_key = "link2wave_secret_key"

def run(cmd, quiet=False):
    p = subprocess.run(shlex.split(cmd), capture_output=True, text=True)
    if p.returncode: raise RuntimeError(p.stderr or cmd)
    return p.stdout.strip()

def yank(url, tmp):
    out = pathlib.Path(tmp) / "%(title)s.%(ext)s"
    yt_dlp_cmd = "yt-dlp"
    venv_yt_dlp = pathlib.Path(".venv/bin/yt-dlp")
    if venv_yt_dlp.exists():
        yt_dlp_cmd = str(venv_yt_dlp)
    run(f'{yt_dlp_cmd} -f bestaudio -o "{out}" "{url}"')
    return next(pathlib.Path(tmp).iterdir())

def trans(src, fmt):
    dst = DEST_DIR / f"{src.stem}.{fmt}"
    if dst.exists(): dst.unlink()
    opts = "-ac 2 -ar 44100" if fmt=="wav" else "-b:a 192k"
    run(f'ffmpeg {FFMPEG_OPTS} -y -i "{src}" {opts} "{dst}"', quiet=True)
    return dst

sha8 = lambda t: hashlib.md5(t.encode()).hexdigest()[:8]
def split(fp, model="htdemucs"):
    out = DEST_DIR/"stems"/sha8(fp); out.mkdir(parents=True, exist_ok=True)
    dev = "--device=cuda" if torch.cuda.is_available() else "--device=cpu"
    demucs.separate.main(["-n", model, dev, "-o", str(out), fp])
    return {p.stem: p for p in out.glob("**/*.wav")}

def rip_audio(url, fmt='mp3'):
    """Download audio from YouTube and convert to specified format"""
    global LAST_RIP, PROCESSING
    PROCESSING = True
    
    try:
        with tempfile.TemporaryDirectory() as tmp:
            raw = yank(url, tmp)
            out = trans(raw, fmt)
            LAST_RIP = str(out)
            PROCESSING = False
            return str(out)
    except Exception as e:
        PROCESSING = False 
        raise e

def separate_audio(audio_file):
    """Separate audio into stems"""
    global CURRENT_STEMS, PROCESSING
    PROCESSING = True
    
    try:
        p = pathlib.Path(audio_file)
        if not p.exists():
            PROCESSING = False
            return None
        
        stems = split(str(p))
        CURRENT_STEMS = stems
        PROCESSING = False
        return stems
    except Exception as e:
        PROCESSING = False
        raise e

# New function for pitch processing using sounddevice
def process_pitch(audio_file, amount=0, correction=False):
    """Process audio with pitch shifting or autotune using sounddevice"""
    try:
        # Check if required libraries are available
        if 'sounddevice' not in sys.modules or 'soundfile' not in sys.modules or 'librosa' not in sys.modules:
            return None, "Required modules (sounddevice, soundfile, librosa) not available"
            
        # Create a temporary file for the output
        fd, output_path = tempfile.mkstemp(suffix='.wav')
        os.close(fd)
        
        # Load the audio file
        y, sr = librosa.load(audio_file, sr=None)
        
        if correction:  # Autotune
            # More sophisticated autotune implementation
            # First, detect the pitch
            pitches, magnitudes = librosa.piptrack(y=y, sr=sr)
            
            # Get the most prominent pitch for each frame
            pitch_frames = []
            for i in range(pitches.shape[1]):
                index = magnitudes[:, i].argmax()
                pitch = pitches[index, i]
                if pitch > 0:  # Filter out non-pitched frames
                    pitch_frames.append(pitch)
            
            # Define musical notes (C major scale)
            A4 = 440.0
            C_MAJOR = [librosa.note_to_hz(n) for n in ['C4', 'D4', 'E4', 'F4', 'G4', 'A4', 'B4', 'C5']]
            
            # Apply correction differently based on amount parameter
            # amount is treated as strength of correction (0-10)
            strength = min(max(amount, 0), 10) / 10.0  # Normalize to 0-1 range
            
            # Process in short frames to apply the correction
            frame_length = 2048
            hop_length = 512
            y_corrected = np.zeros_like(y)
            
            for i in range(0, len(y) - frame_length, hop_length):
                frame = y[i:i+frame_length]
                
                # Get frame pitch
                frame_pitches, frame_magnitudes = librosa.piptrack(y=frame, sr=sr)
                if frame_pitches.size > 0:
                    index = frame_magnitudes.argmax()
                    pitch = frame_pitches.flatten()[index]
                    
                    if pitch > 0:
                        # Find closest note in scale
                        closest_note = min(C_MAJOR, key=lambda x: abs(x - pitch))
                        
                        # Apply correction with variable strength
                        correction_amount = (closest_note - pitch) * strength
                        semitones = 12 * np.log2(1 + correction_amount/pitch)
                        
                        # Apply pitch shift to this frame
                        frame_corrected = librosa.effects.pitch_shift(frame, sr=sr, n_steps=semitones)
                        
                        # Add to output with crossfade
                        if i > 0:  # Apply crossfade except for the first frame
                            # Simple linear crossfade
                            fade_len = min(hop_length, len(frame_corrected))
                            fade_in = np.linspace(0, 1, fade_len)
                            fade_out = np.linspace(1, 0, fade_len)
                            
                            # Apply crossfade
                            y_corrected[i:i+fade_len] *= fade_out
                            y_corrected[i:i+fade_len] += frame_corrected[:fade_len] * fade_in
                            
                            # Add the rest of the frame without crossfade
                            if len(frame_corrected) > fade_len:
                                y_corrected[i+fade_len:i+len(frame_corrected)] = frame_corrected[fade_len:]
                        else:
                            # First frame, no crossfade needed
                            y_corrected[i:i+len(frame_corrected)] = frame_corrected
                    else:
                        # No pitch detected, use original frame
                        y_corrected[i:i+len(frame)] = frame
                else:
                    # No pitch analysis available, use original frame
                    y_corrected[i:i+len(frame)] = frame
            
            # Write the result
            sf.write(output_path, y_corrected, sr)
        else:  # Simple pitch shift
            # Use librosa for pitch shifting
            y_shifted = librosa.effects.pitch_shift(y, sr=sr, n_steps=amount)
            sf.write(output_path, y_shifted, sr)
            
        return output_path, None
    except Exception as e:
        return None, str(e)

def convert_audio(webm_file, fmt='wav'):
    """Convert webm to wav or mp3"""
    try:
        # Create output filename
        output_dir = DEST_DIR / "recordings"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = hashlib.md5(str(webm_file).encode()).hexdigest()[:8]
        output_path = output_dir / f"take_{timestamp}.{fmt}"
        
        # Set options based on format
        opts = "-ac 2 -ar 44100" if fmt=="wav" else "-b:a 192k"
        
        # Run FFmpeg conversion
        run(f'ffmpeg {FFMPEG_OPTS} -y -i "{webm_file}" {opts} "{output_path}"', quiet=True)
        
        return str(output_path), None
    except Exception as e:
        return None, str(e)

# Routes
@app.route('/')
def index():
    # Use the template file instead of the hardcoded template
    return render_template('index.html', 
                           last_rip=LAST_RIP, 
                           stems=CURRENT_STEMS)

@app.route('/rip', methods=['POST'])
def rip():
    if PROCESSING:
        flash('Another operation is in progress. Please wait.', 'error')
        return redirect(url_for('index'))
    
    # Check if form or JSON data
    if request.is_json:
        data = request.get_json()
        url = data.get('url')
        fmt = data.get('format', 'mp3')
    else:
        url = request.form.get('url')
        fmt = request.form.get('format', 'mp3')
    
    if not url or not url.startswith('http'):
        if request.is_json:
            return jsonify({'status': 'error', 'error': 'Please enter a valid YouTube URL'})
        flash('Please enter a valid YouTube URL', 'error')
        return redirect(url_for('index'))
    
    # Start processing in a separate thread
    def process_rip():
        try:
            result = rip_audio(url, fmt)
            app.config['SHOULD_RELOAD'] = True
            # If request expects JSON, prepare response data
            if request.is_json:
                app.config['JSON_RESULT'] = {
                    'status': 'ok',
                    'filename': os.path.basename(result),
                    'filepath': result
                }
        except Exception as e:
            app.config['SHOULD_RELOAD'] = True
            if request.is_json:
                app.config['JSON_RESULT'] = {'status': 'error', 'error': str(e)}
            else:
                flash(f'Error: {str(e)}', 'error')
    
    threading.Thread(target=process_rip).start()
    app.config['ACTIVE_TAB'] = 'rip'
    
    # Handle JSON requests differently
    if request.is_json:
        return jsonify({'status': 'processing'})
    
    return redirect(url_for('index'))

@app.route('/check-rip-status')
def check_rip_status():
    """Check the status of an async rip operation"""
    if not PROCESSING and 'JSON_RESULT' in app.config:
        result = app.config.pop('JSON_RESULT')
        return jsonify(result)
    return jsonify({'status': 'processing'})

@app.route('/separate', methods=['POST'])
def separate():
    if PROCESSING:
        if request.is_json:
            return jsonify({'status': 'error', 'error': 'Another operation is in progress'})
        flash('Another operation is in progress. Please wait.', 'error')
        return redirect(url_for('index'))
    
    # Handle JSON requests for path-based separation
    if request.is_json:
        filepath = request.json.get('filepath')
        if not filepath or not os.path.exists(filepath):
            return jsonify({'status': 'error', 'error': 'File not found'})
        
        # Start processing in a separate thread for API
        def process_api_separation():
            try:
                results = separate_audio(filepath)
                if results:
                    stem_data = [{'name': name, 'path': str(path)} for name, path in results.items()]
                    app.config['JSON_RESULT'] = {'status': 'ok', 'stems': stem_data}
                else:
                    app.config['JSON_RESULT'] = {'status': 'error', 'error': 'Separation failed'}
            except Exception as e:
                app.config['JSON_RESULT'] = {'status': 'error', 'error': str(e)}
        
        threading.Thread(target=process_api_separation).start()
        return jsonify({'status': 'processing'})
    
    # Handle form-based file upload
    if 'audioFile' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('index'))
    
    file = request.files['audioFile']
    
    # If no file selected
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('index'))
    
    # Save the uploaded file
    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, file.filename)
    file.save(file_path)
    
    # Start processing in a separate thread
    def process_separation():
        try:
            results = separate_audio(file_path)
            app.config['SHOULD_RELOAD'] = True
        except Exception as e:
            app.config['SHOULD_RELOAD'] = True
            flash(f'Error during separation: {str(e)}', 'error')
    
    threading.Thread(target=process_separation).start()
    app.config['ACTIVE_TAB'] = 'separate'
    
    return redirect(url_for('index'))

@app.route('/separate-last')
def separate_last():
    if PROCESSING:
        flash('Another operation is in progress. Please wait.', 'error')
        return redirect(url_for('index'))
    
    if not LAST_RIP:
        flash('No audio has been ripped yet', 'error')
        return redirect(url_for('index'))
    
    # Start processing in a separate thread
    def process_separation():
        try:
            results = separate_audio(LAST_RIP)
            app.config['SHOULD_RELOAD'] = True
        except Exception as e:
            app.config['SHOULD_RELOAD'] = True
            flash(f'Error during separation: {str(e)}', 'error')
    
    threading.Thread(target=process_separation).start()
    app.config['ACTIVE_TAB'] = 'separate'
    
    return redirect(url_for('index'))

@app.route('/download')
def download_file():
    file_path = request.args.get('file')
    if not file_path or not os.path.exists(file_path):
        flash('File not found', 'error')
        return redirect(url_for('index'))
    
    return send_file(file_path, as_attachment=True)

@app.route('/download/<stem_name>')
def download_stem(stem_name):
    if stem_name not in CURRENT_STEMS:
        flash('Stem not found', 'error')
        return redirect(url_for('index'))
    
    stem_path = CURRENT_STEMS[stem_name]
    return send_file(str(stem_path), as_attachment=True)

@app.route('/play/<stem_name>')
def play_stem(stem_name):
    if stem_name not in CURRENT_STEMS:
        flash('Stem not found', 'error')
        return redirect(url_for('index'))
    
    stem_path = CURRENT_STEMS[stem_name]
    
    # For web playback, better to send the file
    return send_file(str(stem_path))

@app.route('/status')
def status():
    return jsonify({
        'processing': PROCESSING,
        'tab': app.config.get('ACTIVE_TAB', 'rip'),
        'should_reload': app.config.pop('SHOULD_RELOAD', False)
    })

# New route for saving recordings
@app.route('/save', methods=['POST'])
def save_recording():
    if 'audio' not in request.files:
        return jsonify({'status': 'error', 'error': 'No audio file provided'})
    
    audio_file = request.files['audio']
    
    # Create a temporary file
    temp_dir = tempfile.mkdtemp()
    webm_path = os.path.join(temp_dir, 'take.webm')
    audio_file.save(webm_path)
    
    # Save the file for future download
    DEST_DIR.mkdir(parents=True, exist_ok=True)
    recordings_dir = DEST_DIR / "recordings"
    recordings_dir.mkdir(exist_ok=True)
    
    timestamp = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
    save_path = recordings_dir / f"take_{timestamp}.webm"
    shutil.copy(webm_path, save_path)
    
    return jsonify({'status': 'success', 'filename': save_path.name, 'filepath': str(save_path)})

# New route for converting audio format
@app.route('/convert-audio', methods=['POST'])
def convert_audio_endpoint():
    try:
        data = request.json
        webm_path = data.get('file')
        fmt = data.get('format', 'wav')
        
        if not webm_path or not os.path.exists(webm_path):
            return jsonify({'status': 'error', 'error': 'File not found'})
        
        output_path, error = convert_audio(webm_path, fmt)
        
        if error:
            return jsonify({'status': 'error', 'error': error})
        
        return jsonify({
            'status': 'success', 
            'file': output_path,
            'filename': os.path.basename(output_path)
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)})

# New route for pitch processing
@app.route('/process-pitch', methods=['POST'])
def process_pitch_endpoint():
    try:
        data = request.json
        audio_path = data.get('file')
        correction = data.get('correction', False)
        
        # Handle the amount parameter differently based on correction mode
        if correction:
            # For autotune, amount represents strength (0-10)
            amount = float(data.get('amount', 5.0))  # Default to medium strength
        else:
            # For pitch shift, amount represents semitones
            amount = float(data.get('amount', 0))
        
        if not audio_path or not os.path.exists(audio_path):
            return jsonify({'status': 'error', 'error': 'File not found'})
        
        output_path, error = process_pitch(audio_path, amount, correction)
        
        if error:
            return jsonify({'status': 'error', 'error': error})
        
        return jsonify({
            'status': 'success', 
            'file': output_path,
            'filename': os.path.basename(output_path),
            'processed_with': 'autotune' if correction else 'pitch_shift',
            'amount': amount
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)})

@app.route('/play')
def play_audio():
    """Play audio file from path"""
    path = request.args.get('path')
    if not path or not os.path.exists(path):
        return jsonify({'status': 'error', 'error': 'File not found'})
    
    return send_file(path)

@app.route('/save-stem')
def save_stem():
    """Save stem to user's music folder"""
    path = request.args.get('path')
    if not path or not os.path.exists(path):
        return jsonify({'status': 'error', 'error': 'File not found'})
    
    dest = DEST_DIR / os.path.basename(path)
    shutil.copy(path, dest)
    
    return jsonify({'status': 'success', 'message': f'Saved to {dest}'})

# Function to preview audio using sounddevice
def preview_audio(audio_file, duration=5):
    """Preview audio using sounddevice for direct playback"""
    try:
        if 'sounddevice' not in sys.modules or 'soundfile' not in sys.modules:
            return False, "Required modules (sounddevice, soundfile) not available"
        
        # Get audio info first to use sample rate
        info = sf.info(audio_file)
        sample_rate = info.samplerate
        
        # Load the audio file (just the first few seconds for preview)
        data, sample_rate = sf.read(audio_file, frames=int(duration * sample_rate))
        
        # Play the audio using sounddevice
        sd.play(data, sample_rate)
        sd.wait()  # Wait until the audio is done playing
        
        return True, None
    except Exception as e:
        return False, str(e)

# New route for audio preview
@app.route('/preview-audio', methods=['POST'])
def preview_audio_endpoint():
    try:
        data = request.json
        audio_path = data.get('file')
        duration = float(data.get('duration', 5.0))  # Default to 5 seconds
        
        if not audio_path or not os.path.exists(audio_path):
            return jsonify({'status': 'error', 'error': 'File not found'})
        
        success, error = preview_audio(audio_path, duration)
        
        if not success:
            return jsonify({'status': 'error', 'error': error})
        
        return jsonify({
            'status': 'success',
            'message': f'Played {duration} seconds of audio'
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)})

if __name__ == '__main__':
    import time  # Added for timestamp in recordings
    
    # Initialize configuration
    app.config['SHOULD_RELOAD'] = False
    app.config['ACTIVE_TAB'] = 'rip'
    
    # Run the app on all network interfaces
    app.run(host='0.0.0.0', port=8080, debug=True) 
