from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
import subprocess
import os
import json
import threading
from datetime import datetime
import psutil

app = Flask(__name__, template_folder='templates')
CORS(app, resources={r"/api/*": {"origins": "*"}})

BOTS_FILE = 'bots_config.json'
MAX_LOGS = 1000

bots = []
logs = []
bot_processes = {}

def load_bots():
    global bots
    if os.path.exists(BOTS_FILE):
        with open(BOTS_FILE, 'r') as f:
            bots = json.load(f)
            # Check if any bots are still running
            for bot in bots:
                if bot.get('running') and bot.get('pid'):
                    try:
                        psutil.Process(bot['pid'])
                    except:
                        bot['running'] = False
                        bot['pid'] = None
    else:
        bots = []

def save_bots():
    with open(BOTS_FILE, 'w') as f:
        json.dump(bots, f, indent=2)

def add_log(message, bot_name="System"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {bot_name}: {message}"
    logs.append(log_entry)
    if len(logs) > MAX_LOGS:
        logs.pop(0)
    print(f"LOG: {log_entry}")

def find_venv(bot_path):
    bot_dir = os.path.dirname(bot_path)
    possible_venvs = ['venv', '.venv', 'env', '.env']
    for venv_name in possible_venvs:
        venv_path = os.path.join(bot_dir, venv_name)
        if os.path.isdir(venv_path):
            return venv_path
    return None

def start_bot(idx):
    if idx >= len(bots):
        return False, "Bot not found"

    bot = bots[idx]
    if bot.get('running'):
        return False, "Bot already running"

    bot_path = bot['path']
    bot_dir = os.path.dirname(bot_path)
    bot_name = bot['name']

    if not os.path.exists(bot_path):
        return False, f"Bot file not found: {bot_path}"

    venv_path = find_venv(bot_path)
    if not venv_path:
        return False, "Virtual environment not found. Create one: python -m venv venv"

    python_exe = os.path.join(venv_path, 'bin', 'python')
    if not os.path.exists(python_exe):
        return False, f"Python not found in venv"

    try:
        process = subprocess.Popen(
            [python_exe, bot_path],
            cwd=bot_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        bot['pid'] = process.pid
        bot['running'] = True
        bot_processes[idx] = process
        save_bots()
        add_log(f"Started (PID: {process.pid})", bot_name)

        def stream_output():
            try:
                for line in process.stdout:
                    if line.strip():
                        add_log(line.strip(), bot_name)
            except:
                pass

        thread = threading.Thread(target=stream_output, daemon=True)
        thread.start()

        return True, f"Bot started with PID {process.pid}"

    except Exception as e:
        return False, f"Error starting bot: {str(e)}"

def stop_bot(idx):
    if idx >= len(bots):
        return False, "Bot not found"

    bot = bots[idx]
    if not bot.get('running'):
        return False, "Bot not running"

    try:
        pid = bot['pid']
        process = psutil.Process(pid)
        process.terminate()
        try:
            process.wait(timeout=5)
        except psutil.TimeoutExpired:
            process.kill()
            process.wait()

        bot['running'] = False
        bot['pid'] = None
        if idx in bot_processes:
            del bot_processes[idx]
        save_bots()
        add_log("Stopped", bot['name'])
        return True, "Bot stopped"

    except psutil.NoSuchProcess:
        bot['running'] = False
        bot['pid'] = None
        save_bots()
        return True, "Bot was not running"
    except Exception as e:
        return False, f"Error stopping bot: {str(e)}"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/bots', methods=['GET'])
def get_bots():
    load_bots()
    return jsonify(bots)

@app.route('/api/bots/add', methods=['POST'])
def add_bot_endpoint():
    data = request.json
    path = data.get('path', '').strip()

    if not path:
        return jsonify({'error': 'Path required'}), 400
    
    if not os.path.exists(path):
        return jsonify({'error': f'File not found: {path}'}), 400

    bot_name = os.path.basename(os.path.dirname(path))
    bot = {
        'name': bot_name,
        'path': path,
        'running': False,
        'pid': None
    }

    bots.append(bot)
    save_bots()
    add_log(f"Bot added: {path}", "Manager")
    return jsonify({'message': 'Bot added', 'bot': bot})

@app.route('/api/bots/<int:idx>/start', methods=['POST'])
def start_bot_endpoint(idx):
    success, message = start_bot(idx)
    return jsonify({'message': message, 'success': success}), (200 if success else 400)

@app.route('/api/bots/<int:idx>/stop', methods=['POST'])
def stop_bot_endpoint(idx):
    success, message = stop_bot(idx)
    return jsonify({'message': message, 'success': success}), (200 if success else 400)

@app.route('/api/bots/<int:idx>', methods=['DELETE'])
def delete_bot_endpoint(idx):
    if idx < len(bots):
        if bots[idx].get('running'):
            stop_bot(idx)
        removed = bots.pop(idx)
        save_bots()
        add_log(f"Bot deleted: {removed['name']}", "Manager")
        return jsonify({'message': 'Bot deleted'})
    return jsonify({'error': 'Bot not found'}), 404

@app.route('/api/logs', methods=['GET'])
def get_logs():
    return jsonify(logs)

if __name__ == '__main__':
    load_bots()
    add_log("Bot Manager started", "System")
    print("\n" + "="*50)
    print(" RPi Bot Manager Started!")
    print("="*50)
    print("Access from your computer at:")
    print("http://<RPi-IP>:5000")
    print("="*50 + "\n")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
