#!/usr/bin/env python3
"""Single-file idea sharing web app with a JSON database and generated docs."""

import argparse
import datetime
import hashlib
import http.server
import json
import os
import socketserver
import sys
import urllib.parse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "ideas.json")
DOCS_DIR = os.path.join(BASE_DIR, "docs")
PORT = 5000

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Rural Idea Map</title>
  <link rel="stylesheet" href="/styles.css">
</head>
<body>
  <div class="page">
    <header>
      <h1>Rural Idea Map</h1>
      <p>Type an idea and press Enter to send it into the map.</p>
      <p>Each bubble is a thought: distance = age, size = relevance, direction = idea vector.</p>
    </header>

    <section class="form-panel">
      <form id="idea-form">
        <input id="idea-input" name="idea" type="text" placeholder="Enter your latest thought..." autocomplete="off" />
        <button type="submit">Share</button>
      </form>
      <div class="notes">
        <p>Database file: <code>ideas.json</code></p>
        <p>Export with <code>python run_ideas.py --export</code>, import with <code>python run_ideas.py --import filename.json</code>.</p>
      </div>
    </section>

    <section class="canvas-panel">
      <canvas id="idea-canvas"></canvas>
    </section>

    <footer>
      <a href="/docs/index.html">Read the generated documentation</a>
    </footer>
  </div>
  <script src="/app.js"></script>
</body>
</html>
"""

STYLES_CSS = """html, body { margin: 0; min-height: 100%; background: #070b17; color: #eef6ff; font-family: Inter, system-ui, sans-serif; }
body { display: flex; justify-content: center; align-items: center; padding: 0; }
.page { width: min(1200px, 100%); padding: 24px; box-sizing: border-box; }
header { text-align: center; margin-bottom: 18px; }
header h1 { font-size: clamp(2rem, 4vw, 3.6rem); margin: 0; letter-spacing: 0.04em; }
header p { color: #aac8ff; margin: 12px auto; max-width: 42rem; line-height: 1.6; }
.form-panel { display: grid; gap: 16px; margin-bottom: 18px; }
#idea-form { display: grid; grid-template-columns: 1fr auto; gap: 12px; }
#idea-input { border: 1px solid #2c3f6a; border-radius: 18px; padding: 14px 18px; background: rgba(255,255,255,0.08); color: #f8fcff; font-size: 1rem; }
#idea-input:focus { outline: 2px solid #85b4ff; }
#idea-form button { border: none; border-radius: 18px; padding: 14px 22px; background: #5a85ff; color: white; font-weight: 700; cursor: pointer; }
#idea-form button:hover { background: #3b61e8; }
.notes { color: #a9b7d6; font-size: 0.96rem; }
.notes code { background: rgba(255,255,255,0.08); padding: 3px 6px; border-radius: 6px; }
.canvas-panel { position: relative; min-height: 540px; background: radial-gradient(circle at center, rgba(105, 133, 255, 0.08), transparent 60%), linear-gradient(135deg, rgba(255,255,255,0.04) 1px, transparent 1px), linear-gradient(45deg, rgba(255,255,255,0.03) 1px, transparent 1px); background-size: 32px 32px, 64px 64px, 64px 64px; border-radius: 30px; overflow: hidden; }
canvas { width: 100%; height: 100%; display: block; }
footer { margin-top: 18px; text-align: center; }
footer a { color: #85b4ff; text-decoration: none; }
footer a:hover { text-decoration: underline; }
"""

APP_JS = """const canvas = document.getElementById('idea-canvas');
const ctx = canvas.getContext('2d');
const form = document.getElementById('idea-form');
const input = document.getElementById('idea-input');
let ideas = [];

function resizeCanvas() {
  canvas.width = canvas.clientWidth * devicePixelRatio;
  canvas.height = canvas.clientHeight * devicePixelRatio;
  ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
  draw();
}

function fetchIdeas() {
  return fetch('/api/ideas').then(r => r.json()).then(data => { ideas = data; draw(); });
}

function sendIdea(text) {
  return fetch('/api/ideas', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) })
    .then(r => r.json())
    .then(() => fetchIdeas());
}

form.addEventListener('submit', event => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  sendIdea(text);
  input.value = '';
  input.focus();
});

function draw() {
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  ctx.clearRect(0, 0, width, height);

  const center = { x: width / 2, y: height / 2 };
  const radius = Math.min(width, height) * 0.3;

  ctx.save();
  ctx.translate(center.x, center.y);

  // action radius rings
  ctx.strokeStyle = 'rgba(133, 180, 255, 0.24)';
  ctx.lineWidth = 1.5;
  for (let i = 1; i <= 3; i++) {
    ctx.beginPath();
    ctx.arc(0, 0, radius * i / 3, 0, Math.PI * 2);
    ctx.stroke();
  }

  // central hub
  ctx.fillStyle = 'rgba(94, 156, 255, 0.18)';
  ctx.beginPath();
  ctx.arc(0, 0, 16, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = '#d6e9ff';
  ctx.font = '700 14px Inter, sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText('YOU', 0, 5);

  const now = Date.now();
  ideas.forEach(idea => {
    const ageSeconds = Math.max(1, (now - new Date(idea.created_at).getTime()) / 1000);
    const ageFactor = Math.min(1, ageSeconds / 1800);
    const distance = radius * (0.2 + 0.8 * ageFactor);
    const [dx, dy] = idea.direction;
    const x = dx * distance;
    const y = dy * distance;
    const size = 18 + idea.relevance * 50;

    const gradient = ctx.createRadialGradient(x - size * 0.2, y - size * 0.2, size * 0.2, x, y, size);
    gradient.addColorStop(0, 'rgba(205, 232, 255, 0.95)');
    gradient.addColorStop(1, 'rgba(86, 141, 255, 0.16)');

    ctx.fillStyle = gradient;
    ctx.strokeStyle = 'rgba(255,255,255,0.32)';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(x, y, size, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = '#0f2140';
    ctx.font = `600 ${Math.max(10, Math.min(16, size * 0.35))}px Inter, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const label = idea.text.length > 18 ? idea.text.slice(0, 15) + '…' : idea.text;
    ctx.fillText(label, x, y);
  });

  ctx.restore();
}

window.addEventListener('resize', resizeCanvas);
fetchIdeas().then(resizeCanvas);
"""

DOCS_INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Rural Idea Map Docs</title>
  <style>
    body { font-family: Inter, system-ui, sans-serif; margin: 2rem; background: #051022; color: #e6eefb; }
    a { color: #85b4ff; }
    header { margin-bottom: 1.5rem; }
    section { margin-top: 1.5rem; }
    code { background: rgba(255,255,255,0.08); padding: 0.2rem 0.4rem; border-radius: 5px; }
  </style>
</head>
<body>
  <header>
    <h1>Rural Idea Map Documentation</h1>
    <p>This documentation was generated by <code>run_ideas.py</code> and explains the installation and usage of the single-file app.</p>
  </header>
  <section>
    <h2>Steps</h2>
    <ul>
      <li><a href="step-1.html">Step 1: Create the app and database</a></li>
    </ul>
  </section>
</body>
</html>
"""

DOCS_STEP_1_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Step 1: Initialize the Rural Idea Map</title>
  <style>
    body { font-family: Inter, system-ui, sans-serif; margin: 2rem; background: #051022; color: #e6eefb; }
    h1 { margin-bottom: 0.25rem; }
    code { background: rgba(255,255,255,0.08); padding: 0.2rem 0.4rem; border-radius: 5px; }
    pre { background: rgba(255,255,255,0.06); padding: 1rem; border-radius: 12px; overflow-x: auto; }
    a { color: #85b4ff; }
  </style>
</head>
<body>
  <h1>Step 1: Initialize the Rural Idea Map</h1>
  <p>This app runs from a single script and stores ideas in one JSON database file.</p>
  <h2>How to run</h2>
  <pre><code>python run_ideas.py</code></pre>
  <p>Then open <code>http://localhost:5000</code> in your browser.</p>
  <h2>Database file</h2>
  <p>The app stores ideas in <code>ideas.json</code>. You can export or import it as a complete file:</p>
  <pre><code>python run_ideas.py --export
python run_ideas.py --import ideas.json</code></pre>
  <p>If the file does not exist, the script will create it automatically.</p>
  <p><a href="index.html">Back to docs index</a></p>
</body>
</html>
"""


def ensure_docs():
    os.makedirs(DOCS_DIR, exist_ok=True)
    write_if_missing(os.path.join(DOCS_DIR, 'index.html'), DOCS_INDEX_HTML)
    write_if_missing(os.path.join(DOCS_DIR, 'step-1.html'), DOCS_STEP_1_HTML)


def write_if_missing(path, content):
    if not os.path.exists(path):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)


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
    created_at = datetime.datetime.utcnow().isoformat() + 'Z'
    relevance = max(0.10, min(1.0, 1.0 - len(text) / 180 + 0.15))
    digest = hashlib.sha256(text.encode('utf-8')).digest()
    dx = (digest[0] - 128) / 128
    dy = (digest[1] - 128) / 128
    length = (dx * dx + dy * dy) ** 0.5
    if length < 0.25:
        dx, dy = 0.7, 0.3
    else:
        dx /= length
        dy /= length
    return {
        'id': hashlib.sha1(f"{text}-{created_at}".encode('utf-8')).hexdigest(),
        'text': text,
        'created_at': created_at,
        'relevance': round(relevance, 3),
        'direction': [round(dx, 4), round(dy, 4)],
    }


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
        if path == '/' or path == '/index.html':
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
        if path.startswith('/docs/'):
            return super().do_GET()
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
                if not isinstance(payload, list):
                    raise ValueError('Expected array')
                save_db(payload)
                self.send_json({'status': 'imported', 'count': len(payload)})
            except Exception:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'Failed to import database')
            return
        self.send_response(404)
        self.end_headers()


def run_server(port):
    os.chdir(BASE_DIR)
    handler = IdeaHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"Serving Rural Idea Map at http://127.0.0.1:{port}")
        print(f"Database file: {DB_FILE}")
        print("Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down.")


def export_db(path):
    data = load_db()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Exported {len(data)} ideas to {path}")


def import_db(path):
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError('Import file must contain a JSON array')
    save_db(data)
    print(f"Imported {len(data)} ideas from {path}")


def main():
    parser = argparse.ArgumentParser(description='Run the Rural Idea Map app.')
    parser.add_argument('--port', type=int, default=PORT, help='Port to run the web server on')
    parser.add_argument('--export', nargs='?', const='ideas-export.json', help='Export the JSON database to a file')
    parser.add_argument('--import', dest='import_file', help='Import the JSON database from a file')
    parser.add_argument('--init-docs', action='store_true', help='Create documentation files')
    args = parser.parse_args()

    ensure_docs()

    if args.import_file:
        import_db(os.path.abspath(args.import_file))
        return
    if args.export is not None:
        export_db(os.path.abspath(args.export))
        return

    if not os.path.exists(DB_FILE):
        save_db([])

    run_server(args.port)


if __name__ == '__main__':
    main()
