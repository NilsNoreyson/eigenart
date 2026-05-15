#!/usr/bin/env python3
"""
Self-contained Rural Idea Map app with optional IPFS support.

The script serves a local web app and keeps all idea data in a single JSON file.
It also generates documentation under docs/ automatically.
"""

import argparse
import hashlib
import http.server
import json
import os
import socketserver
import subprocess
import urllib.parse
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, 'ideas.json')
DOCS_DIR = os.path.join(BASE_DIR, 'docs')
HOST = '127.0.0.1'
PORT = 5000

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Rural Idea Map</title>
  <link rel="stylesheet" href="/styles.css" />
</head>
<body>
  <main class="app-shell">
    <section class="panel panel-left">
      <h1>Rural Idea Map</h1>
      <p>Share your latest thought by typing it and pressing Enter. Each idea becomes a bubble on the map.</p>
      <form id="idea-form">
        <textarea id="idea-input" name="idea" rows="4" placeholder="Enter your thought..." autocomplete="off"></textarea>
        <div class="actions">
          <button type="submit">Send</button>
          <button type="button" id="import-button">Import JSON</button>
          <button type="button" id="download-button">Export JSON</button>
        </div>
      </form>
      <div class="help-box">
        <p>Database: <code>ideas.json</code></p>
        <p>Optionally use IPFS from the command line once your local IPFS daemon is running.</p>
        <p><a href="/docs/index.html">Read the generated docs</a></p>
      </div>
      <div id="status" class="status"></div>
    </section>
    <section class="panel panel-right">
      <div class="canvas-container">
        <canvas id="idea-canvas"></canvas>
        <div class="canvas-caption">
          <strong>Action radius</strong>
          <span>Distance shows age, size shows relevance, direction shows idea vector. Click a bubble to read the idea fullscreen.</span>
        </div>
        <div id="idea-modal" class="idea-modal hidden">
          <div class="idea-modal-card">
            <button id="idea-modal-close" class="idea-modal-close" aria-label="Close">×</button>
            <div id="idea-modal-text" class="idea-modal-text"></div>
          </div>
        </div>
      </div>
    </section>
  </main>
  <script src="/app.js"></script>
</body>
</html>
"""

STYLES_CSS = """* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; font-family: Inter, system-ui, sans-serif; color: #e9f2ff; background: radial-gradient(circle at top left, #1f345a, #050912 55%); }
.app-shell { display: grid; grid-template-columns: 380px 1fr; min-height: 100vh; }
.panel { padding: 28px; }
.panel-left { background: rgba(4, 12, 22, 0.95); border-right: 1px solid rgba(255,255,255,0.08); }
.panel-right { position: relative; overflow: hidden; }
h1 { margin-top: 0; font-size: clamp(2rem, 4vw, 3.2rem); }
p { line-height: 1.7; color: #c5d8ff; }
textarea { width: 100%; border-radius: 18px; border: 1px solid rgba(255, 255, 255, 0.10); background: rgba(255,255,255,0.05); color: #eef4ff; padding: 16px; resize: vertical; min-height: 130px; font-size: 1rem; }
textarea:focus { outline: 2px solid rgba(126,153,255,0.8); }
.actions { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 16px; }
button { border: none; border-radius: 999px; padding: 12px 18px; background: linear-gradient(135deg, #6897ff, #3862f3); color: white; cursor: pointer; transition: transform 0.18s ease, filter 0.18s ease; }
button:hover { transform: translateY(-1px); filter: brightness(1.05); }
.help-box { margin-top: 24px; padding: 18px; border-radius: 18px; background: rgba(18, 34, 62, 0.86); border: 1px solid rgba(255,255,255,0.08); }
.help-box code { background: rgba(255,255,255,0.08); padding: 3px 6px; border-radius: 8px; }
.status { margin-top: 22px; min-height: 1.6rem; color: #b5d6ff; }
.canvas-container { width: 100%; height: 100vh; position: relative; }
#idea-canvas { width: 100%; height: 100%; display: block; }
.canvas-caption { position: absolute; left: 24px; bottom: 24px; background: rgba(2, 7, 16, 0.82); border: 1px solid rgba(255,255,255,0.12); border-radius: 18px; padding: 16px 18px; max-width: 320px; }
.canvas-caption strong { display: block; margin-bottom: 6px; }
.idea-modal { position: absolute; inset: 0; display: grid; place-items: center; background: rgba(2, 7, 16, 0.88); padding: 18px; z-index: 20; }
.idea-modal.hidden { display: none; }
.idea-modal-card { width: min(92vw, 760px); max-height: min(88vh, 520px); background: rgba(10, 18, 38, 0.96); border: 1px solid rgba(255,255,255,0.14); border-radius: 24px; padding: 28px; box-shadow: 0 24px 80px rgba(0, 0, 0, 0.35); overflow: auto; }
.idea-modal-close { position: absolute; right: 18px; top: 18px; width: 42px; height: 42px; border: none; border-radius: 50%; background: rgba(255,255,255,0.12); color: #eef4ff; font-size: 1.6rem; cursor: pointer; }
.idea-modal-text { white-space: pre-wrap; line-height: 1.8; color: #f3f7ff; font-size: 1.05rem; }
@media (max-width: 900px) { .app-shell { grid-template-columns: 1fr; } .panel-left { border-right: none; border-bottom: 1px solid rgba(255,255,255,0.08); } .canvas-container { height: calc(100vh - 420px); } }
"""

APP_JS = """const canvas = document.getElementById('idea-canvas');
const ctx = canvas.getContext('2d');
const form = document.getElementById('idea-form');
const input = document.getElementById('idea-input');
const importButton = document.getElementById('import-button');
const downloadButton = document.getElementById('download-button');
const status = document.getElementById('status');
const modal = document.getElementById('idea-modal');
const modalText = document.getElementById('idea-modal-text');
const modalClose = document.getElementById('idea-modal-close');
let ideas = [];
let bubbles = [];

function resizeCanvas() {
  const dpr = window.devicePixelRatio || 1;
  canvas.width = canvas.clientWidth * dpr;
  canvas.height = canvas.clientHeight * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  draw();
}

function showStatus(message, isError = false) {
  status.textContent = message;
  status.style.color = isError ? '#ffadad' : '#b5d6ff';
}

function fetchIdeas() {
  return fetch('/api/ideas')
    .then(response => response.json())
    .then(data => { ideas = data; draw(); })
    .catch(() => showStatus('Unable to load ideas.', true));
}

function submitIdea(text) {
  return fetch('/api/ideas', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text })
  })
    .then(response => {
      if (!response.ok) throw new Error('Submit failed');
      return response.json();
    })
    .then(() => {
      showStatus('Thought shared.');
      return fetchIdeas();
    })
    .catch(() => showStatus('Could not share the thought.', true));
}

function importJson(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = async () => {
      try {
        const json = JSON.parse(reader.result);
        const response = await fetch('/api/import', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ideas: json })
        });
        if (!response.ok) throw new Error('Import failed');
        showStatus('Import completed.');
        await fetchIdeas();
        resolve();
      } catch (error) {
        showStatus('Invalid import file.', true);
        reject(error);
      }
    };
    reader.onerror = () => reject(new Error('Failed to read file'));
    reader.readAsText(file);
  });
}

form.addEventListener('submit', event => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) {
    showStatus('Enter an idea first.', true);
    return;
  }
  submitIdea(text);
  input.value = '';
});

downloadButton.addEventListener('click', () => {
  fetch('/api/export')
    .then(response => response.blob())
    .then(blob => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'ideas.json';
      a.click();
      URL.revokeObjectURL(url);
      showStatus('Export downloaded.');
    })
    .catch(() => showStatus('Export failed.', true));
});

importButton.addEventListener('click', () => {
  const inputEl = document.createElement('input');
  inputEl.type = 'file';
  inputEl.accept = '.json';
  inputEl.onchange = () => {
    const file = inputEl.files[0];
    if (!file) return;
    importJson(file);
  };
  inputEl.click();
});

function drawBackground(width, height) {
  ctx.save();
  const grd = ctx.createRadialGradient(width * 0.25, height * 0.2, 10, width / 2, height / 2, Math.max(width, height));
  grd.addColorStop(0, 'rgba(125, 160, 255, 0.18)');
  grd.addColorStop(1, 'rgba(7, 12, 24, 0.98)');
  ctx.fillStyle = grd;
  ctx.fillRect(0, 0, width, height);

  ctx.strokeStyle = 'rgba(255,255,255,0.08)';
  ctx.lineWidth = 1;
  for (let i = 1; i <= 12; i++) {
    ctx.beginPath();
    ctx.arc(width / 2, height / 2, (Math.min(width, height) / 2) * (i / 12), 0, Math.PI * 2);
    ctx.stroke();
  }
  for (let x = 0; x < width; x += 100) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, height);
    ctx.stroke();
  }
  for (let y = 0; y < height; y += 100) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
  }
  ctx.restore();
}

function draw() {
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  ctx.clearRect(0, 0, width, height);
  drawBackground(width, height);

  const center = { x: width / 2, y: height / 2 };
  bubbles = [];
  ideas.forEach(item => {
    const age = Math.min(1, ((Date.now() / 1000) - new Date(item.created_at).getTime() / 1000) / 3600);
    const distance = 80 + age * (Math.min(width, height) / 2 - 140);
    const [dx, dy] = item.direction;
    const x = center.x + dx * distance;
    const y = center.y + dy * distance;
    const radius = 18 + item.relevance * 48;

    bubbles.push({ x, y, radius, item });

    const bubble = ctx.createRadialGradient(x - radius * 0.2, y - radius * 0.2, 4, x, y, radius);
    bubble.addColorStop(0, 'rgba(255, 255, 255, 0.96)');
    bubble.addColorStop(1, 'rgba(80, 145, 255, 0.18)');
    ctx.fillStyle = bubble;
    ctx.strokeStyle = 'rgba(255,255,255,0.28)';
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = '#0d203d';
    ctx.font = `600 ${Math.max(10, Math.min(14, radius * 0.35))}px Inter, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const label = item.text.length > 18 ? item.text.slice(0, 15) + '…' : item.text;
    ctx.fillText(label, x, y);
  });
}

function getCanvasPointerPosition(event) {
  const rect = canvas.getBoundingClientRect();
  return {
    x: (event.clientX - rect.left) * (canvas.width / rect.width),
    y: (event.clientY - rect.top) * (canvas.height / rect.height)
  };
}

function openIdeaModal(text) {
  modalText.textContent = text;
  modal.classList.remove('hidden');
}

function closeIdeaModal() {
  modal.classList.add('hidden');
}

function handleCanvasClick(event) {
  const { x, y } = getCanvasPointerPosition(event);
  const clicked = bubbles.find(b => {
    const dx = x - b.x;
    const dy = y - b.y;
    return Math.sqrt(dx * dx + dy * dy) <= b.radius;
  });
  if (clicked) {
    openIdeaModal(clicked.item.text);
  }
}

modalClose.addEventListener('click', closeIdeaModal);
modal.addEventListener('click', event => {
  if (event.target === modal) closeIdeaModal();
});

canvas.addEventListener('click', handleCanvasClick);

window.addEventListener('keydown', event => {
  if (event.key === 'Escape') closeIdeaModal();
});

window.addEventListener('resize', resizeCanvas);
fetchIdeas().then(resizeCanvas);
"""

DOCS_INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Rural Idea Map Docs</title>
  <style>
    body { font-family: Inter, system-ui, sans-serif; margin: 2rem; background: #051022; color: #e6eefb; }
    a { color: #85b4ff; }
    ul { list-style: none; padding-left: 0; }
    li { margin-bottom: 0.85rem; }
    code { background: rgba(255,255,255,0.08); padding: 0.2rem 0.4rem; border-radius: 5px; }
  </style>
</head>
<body>
  <h1>Rural Idea Map Documentation</h1>
  <p>Learn how to run the single-file app, store ideas in one JSON file, and optionally use IPFS for backups.</p>
  <ul>
    <li><a href="step-1.html">Step 1: Start the app</a></li>
    <li><a href="step-2.html">Step 2: Export and import the database</a></li>
    <li><a href="step-3.html">Step 3: Visualization details</a></li>
    <li><a href="step-4.html">Step 4: Optional IPFS backup</a></li>
  </ul>
</body>
</html>
"""

DOCS_STEP_1_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Step 1: Start the App</title>
  <style>
    body { font-family: Inter, system-ui, sans-serif; margin: 2rem; background: #051022; color: #e6eefb; }
    a { color: #85b4ff; }
    pre { background: rgba(255,255,255,0.06); padding: 1rem; border-radius: 12px; overflow-x: auto; }
    code { background: rgba(255,255,255,0.08); padding: 0.2rem 0.4rem; border-radius: 5px; }
  </style>
</head>
<body>
  <h1>Step 1: Start the App</h1>
  <p>First create a Python virtual environment in the project folder and install the minimal requirements:</p>
  <pre><code>python -m venv .venv
.venv/Scripts/Activate.ps1
pip install -r requirements.txt</code></pre>
  <p>Then run the app from the single Python file:</p>
  <pre><code>python run_ideas.py</code></pre>
  <p>Open <code>http://127.0.0.1:5000</code> in your browser.</p>
  <p>The app writes the JSON database file <code>ideas.json</code> and generates the <code>docs/</code> folder.</p>
  <p><a href="index.html">Back to docs home</a></p>
</body>
</html>
"""

DOCS_STEP_2_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Step 2: Export and Import</title>
  <style>
    body { font-family: Inter, system-ui, sans-serif; margin: 2rem; background: #051022; color: #e6eefb; }
    a { color: #85b4ff; }
    pre { background: rgba(255,255,255,0.06); padding: 1rem; border-radius: 12px; overflow-x: auto; }
    code { background: rgba(255,255,255,0.08); padding: 0.2rem 0.4rem; border-radius: 5px; }
  </style>
</head>
<body>
  <h1>Step 2: Export and Import</h1>
  <p>The app uses a single JSON file: <code>ideas.json</code>.</p>
  <p>Export the database from the command line:</p>
  <pre><code>python run_ideas.py --export exported-ideas.json</code></pre>
  <p>Import a saved file:</p>
  <pre><code>python run_ideas.py --import exported-ideas.json</code></pre>
  <p>You can also import the same JSON file from the browser interface.</p>
  <p><a href="index.html">Back to docs home</a></p>
</body>
</html>
"""

DOCS_STEP_3_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Step 3: Visualization</title>
  <style>
    body { font-family: Inter, system-ui, sans-serif; margin: 2rem; background: #051022; color: #e6eefb; }
    a { color: #85b4ff; }
    ul { padding-left: 1.2rem; }
  </style>
</head>
<body>
  <h1>Step 3: Visualization</h1>
  <p>The app draws an abstract map-like background and an action radius around the center.</p>
  <ul>
    <li><strong>Distance</strong> is based on the time since the idea was created.</li>
    <li><strong>Size</strong> reflects the idea's relevance.</li>
    <li><strong>Direction</strong> is derived from the idea text.</li>
  </ul>
  <p>This gives each thought a floating bubble shape, like soap and chemistry bubbles on a map.</p>
  <p><a href="index.html">Back to docs home</a></p>
</body>
</html>
"""

DOCS_STEP_4_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Step 4: Optional IPFS Backup</title>
  <style>
    body { font-family: Inter, system-ui, sans-serif; margin: 2rem; background: #051022; color: #e6eefb; }
    a { color: #85b4ff; }
    pre { background: rgba(255,255,255,0.06); padding: 1rem; border-radius: 12px; overflow-x: auto; }
    code { background: rgba(255,255,255,0.08); padding: 0.2rem 0.4rem; border-radius: 5px; }
  </style>
</head>
<body>
  <h1>Step 4: Optional IPFS Backup</h1>
  <p>If you have IPFS installed and a local daemon running, export or import the database using IPFS.</p>
  <pre><code>python run_ideas.py --export-ipfs
python run_ideas.py --import-ipfs Qm...hash</code></pre>
  <p>If IPFS is unavailable, the app still works with the local <code>ideas.json</code> file.</p>
  <p><a href="index.html">Back to docs home</a></p>
</body>
</html>
"""


def write_doc(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def ensure_docs():
    os.makedirs(DOCS_DIR, exist_ok=True)
    write_doc(os.path.join(DOCS_DIR, 'index.html'), DOCS_INDEX_HTML)
    write_doc(os.path.join(DOCS_DIR, 'step-1.html'), DOCS_STEP_1_HTML)
    write_doc(os.path.join(DOCS_DIR, 'step-2.html'), DOCS_STEP_2_HTML)
    write_doc(os.path.join(DOCS_DIR, 'step-3.html'), DOCS_STEP_3_HTML)
    write_doc(os.path.join(DOCS_DIR, 'step-4.html'), DOCS_STEP_4_HTML)


def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []
    return []


def save_db(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def make_idea(text):
    created_at = datetime.utcnow().isoformat() + 'Z'
    relevance = max(0.10, min(1.0, 1.0 - len(text) / 180 + 0.15))
    digest = hashlib.sha256(text.encode('utf-8')).digest()
    dx = (digest[0] - 128) / 128
    dy = (digest[1] - 128) / 128
    length = max((dx * dx + dy * dy) ** 0.5, 0.0001)
    dx /= length
    dy /= length
    return {
        'id': hashlib.sha1(f'{text}-{created_at}'.encode('utf-8')).hexdigest(),
        'text': text,
        'created_at': created_at,
        'relevance': round(relevance, 3),
        'direction': [round(dx, 4), round(dy, 4)],
    }


def run_command(command):
    try:
        return subprocess.check_output(command, stderr=subprocess.STDOUT, cwd=BASE_DIR).decode('utf-8').strip()
    except Exception:
        return None


def ipfs_available():
    return run_command(['ipfs', 'version']) is not None


def ipfs_add(path):
    return run_command(['ipfs', 'add', '-Q', path])


def ipfs_cat(cid):
    return run_command(['ipfs', 'cat', cid])


def export_db(path):
    data = load_db()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f'Exported {len(data)} ideas to {path}')


def import_db(path):
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError('Import file must contain a JSON array')
    save_db(data)
    print(f'Imported {len(data)} ideas from {path}')


def export_ipfs():
    if not ipfs_available():
        print('IPFS is not available. Install IPFS and run a local IPFS daemon.')
        return
    if not os.path.exists(DB_FILE):
        save_db([])
    cid = ipfs_add(DB_FILE)
    if cid:
        print(f'Exported ideas.json to IPFS with CID: {cid}')
    else:
        print('Failed to export to IPFS.')


def import_ipfs(cid):
    if not ipfs_available():
        print('IPFS is not available. Install IPFS and run a local IPFS daemon.')
        return
    content = ipfs_cat(cid)
    if content is None:
        print('Failed to fetch content from IPFS.')
        return
    data = json.loads(content)
    if not isinstance(data, list):
        raise ValueError('IPFS content is not a JSON array')
    save_db(data)
    print(f'Imported {len(data)} ideas from IPFS CID {cid}')


class IdeaHandler(http.server.SimpleHTTPRequestHandler):
    def send_text(self, text, content_type='text/html'):
        encoded = text.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', content_type + '; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def send_json(self, data):
        payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path in ('/', '/index.html'):
            self.send_text(INDEX_HTML)
            return
        if path == '/styles.css':
            self.send_text(STYLES_CSS, 'text/css')
            return
        if path == '/app.js':
            self.send_text(APP_JS, 'application/javascript')
            return
        if path == '/api/ideas':
            self.send_json(load_db())
            return
        if path == '/api/export':
            data = load_db()
            payload = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Disposition', 'attachment; filename="ideas.json"')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8') if length else ''
        if path == '/api/ideas':
            try:
                payload = json.loads(body)
                text = payload.get('text', '').strip()
                if not text:
                    raise ValueError('Empty idea')
            except Exception:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'Invalid request')
                return
            ideas = load_db()
            ideas.append(make_idea(text))
            save_db(ideas)
            self.send_json({'status': 'ok'})
            return
        if path == '/api/import':
            try:
                payload = json.loads(body)
                ideas = payload if isinstance(payload, list) else payload.get('ideas')
                if not isinstance(ideas, list):
                    raise ValueError('Expected a list of ideas')
                save_db(ideas)
                self.send_json({'status': 'imported', 'count': len(ideas)})
            except Exception:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'Failed to import database')
            return
        self.send_response(404)
        self.end_headers()


def run_server(host, port):
    os.chdir(BASE_DIR)
    handler = IdeaHandler
    with socketserver.ThreadingTCPServer((host, port), handler) as httpd:
        print(f'Serving Rural Idea Map at http://{host}:{port}')
        print(f'Database file: {DB_FILE}')
        print('Press Ctrl+C to stop.')
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\nShutting down.')


def main():
    parser = argparse.ArgumentParser(description='Run the Rural Idea Map app.')
    parser.add_argument('--host', default=HOST, help='Host interface to bind the web server to (use 0.0.0.0 for public access)')
    parser.add_argument('--port', type=int, default=PORT, help='Port to run the web server on')
    parser.add_argument('--export', nargs='?', const='ideas-export.json', help='Export the JSON database to a file')
    parser.add_argument('--import', dest='import_file', help='Import the JSON database from a file')
    parser.add_argument('--export-ipfs', action='store_true', help='Export the database to IPFS')
    parser.add_argument('--import-ipfs', dest='import_ipfs', help='Import the database from an IPFS CID')
    parser.add_argument('--init-docs', action='store_true', help='Create documentation files and exit')
    args = parser.parse_args()

    ensure_docs()

    if args.import_file:
        import_db(os.path.abspath(args.import_file))
        return
    if args.export is not None:
        export_db(os.path.abspath(args.export))
        return
    if args.export_ipfs:
        export_ipfs()
        return
    if args.import_ipfs:
        import_ipfs(args.import_ipfs)
        return
    if args.init_docs:
        print('Documentation files created.')
        return

    if not os.path.exists(DB_FILE):
        save_db([])

    run_server(args.host, args.port)


if __name__ == '__main__':
    main()
