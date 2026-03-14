
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
            result = [
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
                for log in self.log_lines[after_id:]
            ]
            return result, len(self.log_lines)

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
    html = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Dev Dashboard — Live Logs</title>
<style>
* { box-sizing: border-box; }
body {
    margin: 0;
    background: #1a202c;
    color: #e2e8f0;
    font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
    font-size: 13px;
}

/* Stats bar */
.stats-bar {
    position: sticky;
    top: 0;
    background: #171923;
    border-bottom: 1px solid #2d3748;
    padding: 6px 12px;
    z-index: 20;
    display: flex;
    align-items: center;
    gap: 16px;
    font-size: 12px;
}
.stats-bar .stat {
    display: flex;
    align-items: center;
    gap: 4px;
}
.stats-bar .stat-val { font-weight: bold; }
.stats-bar .stat-errors { color: #fc8181; cursor: pointer; }
.stats-bar .stat-warnings { color: #f6e05e; }
.stats-bar .stat-total { color: #90cdf4; }
.stats-bar .last-error {
    color: #fc8181;
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 11px;
    opacity: 0.8;
}

/* Controls */
.controls {
    position: sticky;
    top: 30px;
    background: #2d3748;
    padding: 8px 12px;
    z-index: 15;
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
}
.controls input[type="text"] {
    background: #1a202c;
    border: 1px solid #4a5568;
    color: #e2e8f0;
    padding: 4px 8px;
    border-radius: 4px;
    font-family: inherit;
    font-size: 12px;
    width: 200px;
}
.controls button {
    background: #4a5568;
    border: none;
    color: #e2e8f0;
    padding: 4px 10px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 12px;
    font-family: inherit;
}
.controls button:hover { background: #718096; }
.controls button.active { background: #63b3ed; color: #1a202c; }
.controls label {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    cursor: pointer;
}
.controls .spacer { flex: 1; }
.controls .export-btn {
    background: #2a4365;
    font-size: 11px;
    padding: 3px 8px;
}
.controls .export-btn:hover { background: #3182ce; }

/* Log container */
.log-wrapper {
    height: calc(100vh - 70px);
    overflow-y: auto;
    padding: 4px 8px;
}
.empty-state { color: #718096; padding: 20px; text-align: center; }

/* Log lines */
.log-line {
    padding: 4px 8px;
    margin-bottom: 1px;
    border-radius: 2px;
    display: flex;
    align-items: flex-start;
    gap: 8px;
    position: relative;
    cursor: default;
    line-height: 1.4;
}
.log-line:hover { filter: brightness(1.15); }
.log-line.selected { outline: 1px solid #63b3ed; }
.log-line .bookmark-gutter {
    width: 14px;
    min-width: 14px;
    text-align: center;
    cursor: pointer;
    user-select: none;
    opacity: 0.3;
}
.log-line .bookmark-gutter:hover { opacity: 1; }
.log-line.bookmarked .bookmark-gutter { opacity: 1; color: #f6e05e; }
.log-line .timestamp { color: #718096; white-space: nowrap; }
.log-line .log-content { flex: 1; word-break: break-all; }

.error { background: #742a2a; }
.warning { background: #744210; }
.info { background: #2a4365; }
.highlight { background: #fef08a; color: #1a202c; padding: 0 1px; border-radius: 2px; }
.filter-hidden { display: none !important; }

/* Repeat badge */
.repeat-badge {
    background: #805ad5;
    color: white;
    font-size: 10px;
    padding: 1px 5px;
    border-radius: 8px;
    margin-left: 6px;
    cursor: pointer;
    white-space: nowrap;
}

/* File refs */
.file-ref { font-weight: bold; text-decoration: underline; color: #90cdf4; }

/* Traceback */
.traceback-detail {
    display: none;
    margin-top: 4px;
    padding: 6px 10px;
    background: rgba(0,0,0,0.3);
    border-left: 3px solid #fc8181;
    border-radius: 2px;
    font-size: 12px;
}
.traceback-detail.expanded { display: block; }
.traceback-toggle {
    cursor: pointer;
    color: #fc8181;
    font-size: 11px;
    margin-left: 6px;
    user-select: none;
}

/* JSON collapsible */
.json-collapsed {
    color: #68d391;
    cursor: pointer;
    font-size: 12px;
}
.json-expanded {
    display: none;
    margin-top: 4px;
    padding: 6px 10px;
    background: rgba(0,0,0,0.3);
    border-left: 3px solid #68d391;
    border-radius: 2px;
    white-space: pre;
    font-size: 12px;
    color: #68d391;
}
.json-expanded.expanded { display: block; }

/* Keyboard help overlay */
.help-overlay {
    display: none;
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.7);
    z-index: 100;
    justify-content: center;
    align-items: center;
}
.help-overlay.visible { display: flex; }
.help-box {
    background: #2d3748;
    border: 1px solid #4a5568;
    border-radius: 8px;
    padding: 24px;
    max-width: 400px;
    width: 90%;
}
.help-box h3 { margin-top: 0; color: #63b3ed; }
.help-box table { width: 100%; }
.help-box td { padding: 4px 8px; }
.help-box kbd {
    background: #4a5568;
    padding: 2px 6px;
    border-radius: 3px;
    font-family: inherit;
    font-size: 12px;
}
</style>
</head>
<body>

<div class="stats-bar" id="statsBar">
    <div class="stat stat-total"><span>Total:</span> <span class="stat-val" id="statTotal">0</span></div>
    <div class="stat stat-errors" onclick="jumpToError()"><span>Errors:</span> <span class="stat-val" id="statErrors">0</span></div>
    <div class="stat stat-warnings"><span>Warnings:</span> <span class="stat-val" id="statWarnings">0</span></div>
    <div class="stat"><span>Duration:</span> <span class="stat-val" id="statDuration">0s</span></div>
    <div class="last-error" id="lastError"></div>
</div>

<div class="controls">
    <input type="text" id="searchInput" placeholder="Search logs..." oninput="searchLogs()">
    <label><input type="checkbox" id="regexToggle"> Regex</label>
    <button onclick="filterLogs('all')" id="filterAll" class="active">All</button>
    <button onclick="filterLogs('error')" id="filterError">Errors</button>
    <button onclick="filterLogs('warning')" id="filterWarning">Warnings</button>
    <button onclick="filterLogs('info')" id="filterInfo">Info</button>
    <label>
        <input type="checkbox" id="autoScroll" checked>
        Auto-scroll
    </label>
    <div class="spacer"></div>
    <button class="export-btn" onclick="location.href='/api/export?format=log'">Export .log</button>
    <button class="export-btn" onclick="location.href='/api/export?format=html'">Export .html</button>
    <button onclick="toggleHelp()" title="Keyboard shortcuts (?)">?</button>
</div>

<div class="log-wrapper" id="logContainer">
    <div class="empty-state">Waiting for logs…</div>
</div>

<div class="help-overlay" id="helpOverlay" onclick="if(event.target===this)toggleHelp()">
    <div class="help-box">
        <h3>Keyboard Shortcuts</h3>
        <table>
            <tr><td><kbd>j</kbd> / <kbd>k</kbd></td><td>Next / previous log line</td></tr>
            <tr><td><kbd>e</kbd> / <kbd>E</kbd></td><td>Next / previous error</td></tr>
            <tr><td><kbd>n</kbd> / <kbd>N</kbd></td><td>Next / previous search match</td></tr>
            <tr><td><kbd>b</kbd></td><td>Next bookmark</td></tr>
            <tr><td><kbd>?</kbd></td><td>Toggle this help</td></tr>
            <tr><td><kbd>Esc</kbd></td><td>Close overlay / clear search</td></tr>
        </table>
    </div>
</div>

<script>
let currentFilter = 'all';
let allLogs = [];
let bookmarks = new Set();
let selectedIdx = -1;
let currentSearchTerm = '';
let startTime = Date.now();

function escapeRegex(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
}

function highlightHtml(html, term) {
    if (!term) return html;
    const useRegex = document.getElementById('regexToggle').checked;
    let re;
    try {
        re = useRegex ? new RegExp('(' + term + ')', 'gi') : new RegExp('(' + escapeRegex(term) + ')', 'gi');
    } catch(e) { return html; }
    return html.replace(re, '<span class="highlight">$1</span>');
}

function matchesSearch(text, term) {
    if (!term) return true;
    const useRegex = document.getElementById('regexToggle').checked;
    if (useRegex) {
        try { return new RegExp(term, 'i').test(text); } catch(e) { return false; }
    }
    return text.toLowerCase().includes(term.toLowerCase());
}

function highlightFileRefs(html, fileRefs) {
    if (!fileRefs || !fileRefs.length) return html;
    fileRefs.forEach(ref => {
        const pattern = ref.file + ':' + ref.line;
        const escaped = escapeHtml(pattern);
        html = html.replace(escaped, '<span class="file-ref">' + escaped + '</span>');
    });
    return html;
}

function renderLogLine(log, idx) {
    const div = document.createElement('div');
    div.className = 'log-line ' + log.type;
    div.dataset.type = log.type;
    div.dataset.content = log.content;
    div.dataset.idx = idx;

    const gutter = '<span class="bookmark-gutter" onclick="toggleBookmark(' + idx + ',event)">&#9733;</span>';
    const ts = '<span class="timestamp">[' + log.timestamp + ']</span>';

    let content = log.html_content;
    content = highlightFileRefs(content, log.file_refs);
    content = highlightHtml(content, currentSearchTerm);

    let extra = '';

    // Repeat badge
    if (log.repeat_count > 1) {
        extra += '<span class="repeat-badge">&times;' + log.repeat_count + '</span>';
    }

    // Traceback
    if (log.traceback_lines && log.traceback_lines.length > 0) {
        extra += '<span class="traceback-toggle" onclick="toggleTraceback(this)">[+' + log.traceback_lines.length + ' trace lines]</span>';
        extra += '<div class="traceback-detail">' + log.traceback_lines.join('<br>') + '</div>';
    }

    // JSON
    if (log.is_json && log.json_pretty) {
        const prettyEscaped = escapeHtml(log.json_pretty);
        extra += '<div class="json-collapsed" onclick="toggleJson(this)">[JSON — click to expand]</div>';
        extra += '<div class="json-expanded"><pre>' + prettyEscaped + '</pre></div>';
    }

    div.innerHTML = gutter + ' ' + ts + ' <span class="log-content">' + content + '</span>' + extra;

    if (bookmarks.has(idx)) div.classList.add('bookmarked');

    return div;
}

function toggleTraceback(el) {
    const detail = el.nextElementSibling;
    detail.classList.toggle('expanded');
    el.textContent = detail.classList.contains('expanded')
        ? '[-collapse trace]'
        : '[+' + detail.querySelectorAll('br').length + ' trace lines]';
}

function toggleJson(el) {
    const expanded = el.nextElementSibling;
    expanded.classList.toggle('expanded');
    el.textContent = expanded.classList.contains('expanded') ? '[JSON — click to collapse]' : '[JSON — click to expand]';
}

function toggleBookmark(idx, e) {
    e.stopPropagation();
    if (bookmarks.has(idx)) bookmarks.delete(idx);
    else bookmarks.add(idx);
    const line = document.querySelector('.log-line[data-idx="' + idx + '"]');
    if (line) line.classList.toggle('bookmarked');
}

function updateStats() {
    let total = 0, errors = 0, warnings = 0, lastErr = '';
    allLogs.forEach(l => {
        total += l.repeat_count || 1;
        if (l.type === 'error') { errors++; lastErr = l.content; }
        if (l.type === 'warning') warnings++;
    });
    document.getElementById('statTotal').textContent = total;
    document.getElementById('statErrors').textContent = errors;
    document.getElementById('statWarnings').textContent = warnings;
    const dur = Math.floor((Date.now() - startTime) / 1000);
    document.getElementById('statDuration').textContent = dur + 's';
    document.getElementById('lastError').textContent = lastErr ? 'Last: ' + lastErr : '';
}

function appendNewLogs(logs) {
    const c = document.getElementById('logContainer');
    c.querySelector('.empty-state')?.remove();

    logs.forEach(l => {
        const idx = allLogs.length;
        allLogs.push(l);
        const div = renderLogLine(l, idx);

        if (currentFilter !== 'all' && l.type !== currentFilter)
            div.classList.add('filter-hidden');
        if (!matchesSearch(l.content, currentSearchTerm))
            div.classList.add('filter-hidden');

        c.appendChild(div);
    });

    updateStats();

    if (document.getElementById('autoScroll').checked) {
        c.scrollTop = c.scrollHeight;
    }
}

function refilter() {
    document.querySelectorAll('.log-line').forEach(el => {
        const ok = (currentFilter === 'all' || el.dataset.type === currentFilter) &&
                   matchesSearch(el.dataset.content, currentSearchTerm);
        el.classList.toggle('filter-hidden', !ok);
    });
}

function searchLogs() {
    currentSearchTerm = document.getElementById('searchInput').value.trim();
    refilter();
    // Re-render content to update highlighting
    document.querySelectorAll('.log-line').forEach(el => {
        const idx = parseInt(el.dataset.idx);
        const log = allLogs[idx];
        if (!log) return;
        const contentEl = el.querySelector('.log-content');
        if (contentEl) {
            let html = log.html_content;
            html = highlightFileRefs(html, log.file_refs);
            html = highlightHtml(html, currentSearchTerm);
            contentEl.innerHTML = html;
        }
    });
}

function filterLogs(t) {
    currentFilter = t;
    document.querySelectorAll('.controls button').forEach(b => b.classList.remove('active'));
    const btn = document.getElementById('filter' + t.charAt(0).toUpperCase() + t.slice(1));
    if (btn) btn.classList.add('active');
    refilter();
}

function selectLine(idx) {
    document.querySelectorAll('.log-line.selected').forEach(el => el.classList.remove('selected'));
    const el = document.querySelector('.log-line[data-idx="' + idx + '"]');
    if (el && !el.classList.contains('filter-hidden')) {
        el.classList.add('selected');
        el.scrollIntoView({ block: 'nearest' });
        selectedIdx = idx;
    }
}

function getVisibleLines() {
    return [...document.querySelectorAll('.log-line:not(.filter-hidden)')];
}

function jumpToError(dir) {
    const visible = getVisibleLines();
    const errors = visible.filter(el => el.dataset.type === 'error');
    if (!errors.length) return;
    if (dir === 'prev') {
        const prev = errors.reverse().find(el => parseInt(el.dataset.idx) < selectedIdx);
        if (prev) selectLine(parseInt(prev.dataset.idx));
        else selectLine(parseInt(errors[0].dataset.idx));
    } else {
        const next = errors.find(el => parseInt(el.dataset.idx) > selectedIdx);
        if (next) selectLine(parseInt(next.dataset.idx));
        else selectLine(parseInt(errors[0].dataset.idx));
    }
}

function jumpToSearchMatch(dir) {
    if (!currentSearchTerm) return;
    const visible = getVisibleLines().filter(el => matchesSearch(el.dataset.content, currentSearchTerm));
    if (!visible.length) return;
    if (dir === 'prev') {
        const prev = [...visible].reverse().find(el => parseInt(el.dataset.idx) < selectedIdx);
        if (prev) selectLine(parseInt(prev.dataset.idx));
        else selectLine(parseInt(visible[visible.length - 1].dataset.idx));
    } else {
        const next = visible.find(el => parseInt(el.dataset.idx) > selectedIdx);
        if (next) selectLine(parseInt(next.dataset.idx));
        else selectLine(parseInt(visible[0].dataset.idx));
    }
}

function jumpToBookmark() {
    if (!bookmarks.size) return;
    const sorted = [...bookmarks].sort((a, b) => a - b);
    const next = sorted.find(i => i > selectedIdx);
    selectLine(next !== undefined ? next : sorted[0]);
}

function toggleHelp() {
    document.getElementById('helpOverlay').classList.toggle('visible');
}

// Keyboard shortcuts
document.addEventListener('keydown', function(e) {
    const tag = e.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA') {
        if (e.key === 'Escape') {
            e.target.blur();
            document.getElementById('searchInput').value = '';
            currentSearchTerm = '';
            refilter();
        }
        return;
    }

    const visible = getVisibleLines();

    switch(e.key) {
        case 'j': {
            if (!visible.length) break;
            const cur = visible.findIndex(el => parseInt(el.dataset.idx) === selectedIdx);
            const next = cur < visible.length - 1 ? cur + 1 : 0;
            selectLine(parseInt(visible[next].dataset.idx));
            break;
        }
        case 'k': {
            if (!visible.length) break;
            const cur = visible.findIndex(el => parseInt(el.dataset.idx) === selectedIdx);
            const prev = cur > 0 ? cur - 1 : visible.length - 1;
            selectLine(parseInt(visible[prev].dataset.idx));
            break;
        }
        case 'e': jumpToError('next'); break;
        case 'E': jumpToError('prev'); break;
        case 'n': jumpToSearchMatch('next'); break;
        case 'N': jumpToSearchMatch('prev'); break;
        case 'b': jumpToBookmark(); break;
        case '?': toggleHelp(); break;
        case 'Escape':
            if (document.getElementById('helpOverlay').classList.contains('visible'))
                toggleHelp();
            break;
    }
});

// SSE streaming
async function init() {
    // Initial bulk load
    try {
        const logs = await (await fetch('/api/logs')).json();
        appendNewLogs(logs);
    } catch(e) {}

    // SSE for live updates
    const es = new EventSource('/api/stream');
    es.onmessage = function(e) {
        try {
            const logs = JSON.parse(e.data);
            appendNewLogs(logs);
        } catch(err) {}
    };
    es.onerror = function() {
        // Fallback to polling if SSE fails
        es.close();
        setInterval(async () => {
            try {
                const logs = await (await fetch('/api/logs')).json();
                const newLogs = logs.slice(allLogs.length);
                if (newLogs.length) appendNewLogs(newLogs);
            } catch(e) {}
        }, 500);
    };
}

init();
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
    import atexit

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", "-p", type=int, default=8765)
    args = parser.parse_args()

    html_path = os.path.join(
        tempfile.gettempdir(),
        f"log_aggregator_{os.getpid()}.html"
    )
    atexit.register(lambda: os.unlink(html_path) if os.path.exists(html_path) else None)

    agg = LogAggregator(args.port)
    run_server(agg, args.port)
    agg.capture_input()


if __name__ == "__main__":
    main()
