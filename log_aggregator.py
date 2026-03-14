
#!/usr/bin/env python3
"""
Real-time Log Aggregator - Displays piped output as live-updating HTML
"""

import sys
import datetime
import argparse
import webbrowser
import threading
import json
import time
import os
import re
import tempfile
from http.server import BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import http.server

from ansi2html import Ansi2HTMLConverter


class LogAggregator:
    def __init__(self, port=8765):
        self.port = port
        self.log_lines = []
        self.start_time = datetime.datetime.now()
        self.lock = threading.Lock()
        self.running = True
        self.ansi_conv = Ansi2HTMLConverter(inline=True, scheme="xterm")
        self._file_ref_re = re.compile(
            r'(?:^|[\s\'"\(])([a-zA-Z0-9_./\\-]+\.[a-zA-Z]{1,5})'
            r'[:\(](\d+)[\),:]?'
        )
        self._traceback_active = False
        self._sse_event = threading.Event()
        self._last_id = 0

    def add_log_line(self, line):
        with self.lock:
            content = line.rstrip("\n")
            line_type = self._classify_line(line)
            html_content = self.ansi_conv.convert(content, full=False)
            file_refs = self._extract_file_refs(content)
            is_json, json_pretty = self._try_parse_json(content)

            # Repetition squashing
            if self.log_lines and self.log_lines[-1]["content"] == content:
                self.log_lines[-1]["repeat_count"] += 1
                return

            # Stack trace grouping
            is_trace_line = self._is_traceback_line(content)
            if is_trace_line and self.log_lines and self.log_lines[-1].get("traceback_lines") is not None:
                self.log_lines[-1]["traceback_lines"].append(html_content)
                self.log_lines[-1]["content_raw"] = content
                return

            entry = {
                "time": datetime.datetime.now(),
                "content": content,
                "html_content": html_content,
                "type": line_type,
                "file_refs": file_refs,
                "is_json": is_json,
                "json_pretty": json_pretty,
                "repeat_count": 1,
                "traceback_lines": [] if self._is_traceback_start(content) else None,
            }
            self.log_lines.append(entry)
            self._last_id = len(self.log_lines)
            self._sse_event.set()
            self._sse_event.clear()

    def get_logs_since(self, after_id):
        with self.lock:
            logs = self.get_logs_json()[after_id:]
            return logs, len(self.log_lines)

    def get_logs_json(self):
        with self.lock:
            return [
                {
                    "timestamp": log["time"].strftime("%H:%M:%S.%f")[:-3],
                    "content": log["content"],
                    "html_content": log["html_content"],
                    "type": log["type"],
                    "file_refs": log["file_refs"],
                    "is_json": log["is_json"],
                    "json_pretty": log.get("json_pretty"),
                    "repeat_count": log["repeat_count"],
                    "traceback_lines": log.get("traceback_lines"),
                }
                for log in self.log_lines
            ]

    def get_stats(self):
        with self.lock:
            return {
                "total": len(self.log_lines),
                "errors": sum(1 for l in self.log_lines if l["type"] == "error"),
                "warnings": sum(1 for l in self.log_lines if l["type"] == "warning"),
                "duration": (datetime.datetime.now() - self.start_time).total_seconds(),
            }

    def _classify_line(self, line):
        l = line.lower()
        if any(k in l for k in ("error", "exception", "traceback", "fatal", "critical")):
            return "error"
        if any(k in l for k in ("warn", "warning", "deprecated")):
            return "warning"
        return "info"

    def _is_traceback_start(self, line):
        l = line.strip()
        return l == "Traceback (most recent call last):" or l.startswith("ERROR ") and "Traceback" in l

    def _is_traceback_line(self, line):
        s = line.strip()
        return (
            s.startswith("File ") or
            s.startswith("at ") or
            s.startswith("in ") or
            (len(s) > 0 and s[0] == '^') or
            s.startswith("raise ") or
            s.startswith("| ") or
            bool(re.match(r'^\d+[:|\s]', s))
        )

    def _extract_file_refs(self, line):
        return [{"file": m.group(1), "line": int(m.group(2))} for m in self._file_ref_re.finditer(line)]

    def _try_parse_json(self, line):
        stripped = line.strip()
        if stripped.startswith('{') or stripped.startswith('['):
            try:
                parsed = json.loads(stripped)
                return True, json.dumps(parsed, indent=2)
            except (json.JSONDecodeError, ValueError):
                pass
        return False, None

    def capture_input(self):
        print(f"🌐 http://localhost:{self.port}")
        try:
            for line in sys.stdin:
                print(line, end="")
                self.add_log_line(line)
        except KeyboardInterrupt:
            self.running = False


class LogRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path == "/":
            self.serve_html()
        elif self.path == "/api/logs":
            self.serve_json(self.server.aggregator.get_logs_json())
        elif self.path.startswith("/api/stream"):
            self.serve_sse()
        elif self.path.startswith("/api/export"):
            self.serve_export()
        else:
            self.send_error(404)

    def serve_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        last_id = 0
        agg = self.server.aggregator
        try:
            while agg.running:
                logs, current_id = agg.get_logs_since(last_id)
                if logs:
                    data = json.dumps(logs)
                    self.wfile.write(f"id: {current_id}\ndata: {data}\n\n".encode())
                    self.wfile.flush()
                    last_id = current_id
                agg._sse_event.wait(timeout=0.3)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def serve_export(self):
        from urllib.parse import urlparse, parse_qs
        params = parse_qs(urlparse(self.path).query)
        fmt = params.get("format", ["log"])[0]
        logs = self.server.aggregator.get_logs_json()

        if fmt == "html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Disposition", "attachment; filename=logs.html")
            self.end_headers()
            html = "<html><head><style>body{background:#1a202c;color:#e2e8f0;font-family:monospace;padding:10px;}"
            html += ".error{background:#742a2a;padding:4px;margin:2px 0;}.warning{background:#744210;padding:4px;margin:2px 0;}"
            html += ".info{background:#2a4365;padding:4px;margin:2px 0;}</style></head><body>"
            for log in logs:
                html += f'<div class="{log["type"]}">[{log["timestamp"]}] {log["html_content"]}</div>'
            html += "</body></html>"
            self.wfile.write(html.encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Disposition", "attachment; filename=logs.txt")
            self.end_headers()
            for log in logs:
                self.wfile.write(f'[{log["timestamp"]}] {log["content"]}\n'.encode())

    def serve_json(self, payload):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def serve_html(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        with open(self.server.html_path, "rb") as f:
            self.wfile.write(f.read())


def generate_html(path):
    html = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Live Logs</title>
<style>
body {
    margin: 0;
    background: #1a202c;
    color: #e2e8f0;
    font-family: monospace;
}
.controls {
    position: sticky;
    top: 0;
    background: #2d3748;
    padding: 10px;
    z-index: 10;
}
.log-wrapper {
    height: calc(100vh - 60px);
    overflow-y: auto;
    padding: 10px;
}
.log-line {
    padding: 6px;
    margin-bottom: 2px;
}
.error { background: #742a2a; }
.warning { background: #744210; }
.info { background: #2a4365; }
.highlight { background: #fef08a; color: black; }
.filter-hidden { display: none; }
label { margin-left: 10px; }
</style>
</head>
<body>

<div class="controls">
    <input id="searchInput" placeholder="search" oninput="searchLogs()">
    <button onclick="filterLogs('all')">All</button>
    <button onclick="filterLogs('error')">Errors</button>
    <button onclick="filterLogs('warning')">Warnings</button>
    <button onclick="filterLogs('info')">Info</button>
    <label>
        <input type="checkbox" id="autoScroll" checked>
        Auto-scroll
    </label>
</div>

<div class="log-wrapper" id="logContainer">
    <div class="empty-state">Waiting for logs…</div>
</div>

<script>
let currentFilter = 'all';
let lastLogCount = 0;
let currentSearchTerm = '';

function escapeRegex(str) {
    return str.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&');
}

function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
}

function highlightText(text, term) {
    if (!term) return escapeHtml(text);
    const r = new RegExp('(' + escapeRegex(term) + ')', 'gi');
    return escapeHtml(text).replace(r, '<span class="highlight">$1</span>');
}

function matchesSearch(text, term) {
    return !term || text.toLowerCase().includes(term.toLowerCase());
}

function appendLogs(logs) {
    const c = document.getElementById('logContainer');
    c.querySelector('.empty-state')?.remove();

    logs.slice(lastLogCount).forEach(l => {
        const d = document.createElement('div');
        d.className = `log-line ${l.type}`;
        d.dataset.type = l.type;
        d.dataset.content = l.content;

        d.innerHTML =
            `<span>[${l.timestamp}]</span> ` +
            `<span class="log-content">${highlightText(l.content, currentSearchTerm)}</span>`;

        if (currentFilter !== 'all' && l.type !== currentFilter)
            d.classList.add('filter-hidden');

        if (!matchesSearch(l.content, currentSearchTerm))
            d.classList.add('filter-hidden');

        c.appendChild(d);
    });

    lastLogCount = logs.length;

    if (document.getElementById('autoScroll').checked) {
        c.scrollTop = c.scrollHeight;
    }
}

function searchLogs() {
    currentSearchTerm = document.getElementById('searchInput').value.trim();
    document.querySelectorAll('.log-line').forEach(l => {
        const ok =
            (currentFilter === 'all' || l.dataset.type === currentFilter) &&
            matchesSearch(l.dataset.content, currentSearchTerm);

        l.classList.toggle('filter-hidden', !ok);
        if (ok)
            l.querySelector('.log-content').innerHTML =
                highlightText(l.dataset.content, currentSearchTerm);
    });
}

function filterLogs(t) {
    currentFilter = t;
    searchLogs();
}

async function poll() {
    const logs = await (await fetch('/api/logs')).json();
    appendLogs(logs);
}

setInterval(poll, 500);
poll();
</script>

</body>
</html>
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


class ThreadedHTTPServer(ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def run_server(aggregator, port):
    html_path = os.path.join(
        tempfile.gettempdir(),
        f"log_aggregator_{os.getpid()}.html"
    )
    generate_html(html_path)

    server = ThreadedHTTPServer(("localhost", port), LogRequestHandler)
    server.aggregator = aggregator
    server.html_path = html_path

    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.3)
    webbrowser.open(f"http://localhost:{port}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", "-p", type=int, default=8765)
    args = parser.parse_args()

    agg = LogAggregator(args.port)
    run_server(agg, args.port)
    agg.capture_input()


if __name__ == "__main__":
    main()
