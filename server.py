import json
import os
import re
import sqlite3
import urllib.parse
import urllib.request
from collections import Counter
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime

DB_PATH = os.getenv('SEO_DB_PATH', 'seo_reports.db')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')

class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ''
        self.meta_description = ''
        self.h1 = []
        self.h2 = []
        self.links = []
        self.images_missing_alt = 0
        self.images_total = 0
        self.in_title = False
        self.current_tag = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.current_tag = tag
        if tag == 'meta' and attrs.get('name', '').lower() == 'description':
            self.meta_description = attrs.get('content', '')
        if tag == 'a' and attrs.get('href'):
            self.links.append(attrs['href'])
        if tag == 'img':
            self.images_total += 1
            if not attrs.get('alt', '').strip():
                self.images_missing_alt += 1
        if tag == 'title':
            self.in_title = True

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
        self.current_tag = None

    def handle_data(self, data):
        text = data.strip()
        if not text:
            return
        if self.in_title:
            self.title += text
        elif self.current_tag == 'h1':
            self.h1.append(text)
        elif self.current_tag == 'h2':
            self.h2.append(text)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            created_at TEXT NOT NULL,
            report_json TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()


def fetch_html(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 SEO Dashboard'})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.status, resp.read().decode('utf-8', errors='ignore')


def score_report(p):
    score = 100
    issues = []
    if not p.title or len(p.title) < 20 or len(p.title) > 65:
        score -= 15
        issues.append('Title length should be between 20 and 65 characters.')
    if not p.meta_description or len(p.meta_description) < 120 or len(p.meta_description) > 160:
        score -= 15
        issues.append('Meta description should be 120-160 characters.')
    if len(p.h1) != 1:
        score -= 15
        issues.append('Page should have exactly one H1 heading.')
    if len(p.h2) == 0:
        score -= 10
        issues.append('Add H2 headings for better structure.')
    if p.images_total and p.images_missing_alt > 0:
        score -= min(20, p.images_missing_alt * 2)
        issues.append(f'{p.images_missing_alt} images are missing alt text.')
    if len(p.links) < 3:
        score -= 10
        issues.append('Add more internal links to improve crawlability.')
    return max(score, 0), issues


def keywords_from_text(html):
    words = re.findall(r"[a-zA-Z]{4,}", html.lower())
    stop = set('this that with from have your about into than then they them were been when what where which while would should could there their'.split())
    words = [w for w in words if w not in stop]
    return [w for w, _ in Counter(words).most_common(12)]


def ai_recommendations(url, issues, keywords):
    base = [
        {'opportunity': 'Improve metadata quality', 'fix': 'Rewrite title/meta around primary keyword and value proposition.', 'priority': 'High'},
        {'opportunity': 'Strengthen content structure', 'fix': 'Use one H1 and add descriptive H2 sections matching user intent.', 'priority': 'High'},
        {'opportunity': 'Increase topical authority', 'fix': f'Create supporting pages around: {", ".join(keywords[:5])}', 'priority': 'Medium'},
    ]
    if OPENAI_API_KEY:
        base.append({'opportunity': 'AI key detected', 'fix': 'You can extend this to generate page-specific rewrites with OpenAI.', 'priority': 'Low'})
    if issues:
        base.append({'opportunity': 'Quick technical wins', 'fix': issues[0], 'priority': 'High'})
    return base


def generate_report(url):
    status, html = fetch_html(url)
    p = Parser()
    p.feed(html)
    score, issues = score_report(p)
    keywords = keywords_from_text(html)
    recommendations = ai_recommendations(url, issues, keywords)
    return {
        'url': url,
        'http_status': status,
        'seo_score': score,
        'title': p.title,
        'meta_description': p.meta_description,
        'h1': p.h1,
        'h2_count': len(p.h2),
        'links_found': len(p.links),
        'images_total': p.images_total,
        'images_missing_alt': p.images_missing_alt,
        'issues': issues,
        'keyword_opportunities': keywords,
        'recommendations': recommendations,
        'generated_at': datetime.utcnow().isoformat() + 'Z'
    }


HTML_PAGE = """<!doctype html><html><head><meta charset='utf-8'/><title>SEO Dashboard</title>
<style>body{font-family:Arial;margin:24px;max-width:1000px}.card{border:1px solid #ddd;border-radius:8px;padding:16px;margin:12px 0}input{width:70%;padding:8px}button{padding:8px 12px}pre{background:#f6f8fa;padding:12px;border-radius:8px;white-space:pre-wrap}</style></head>
<body><h1>Local SEO Dashboard</h1><p>Enter a website URL and get technical issues, opportunities and fixes.</p>
<input id='url' placeholder='https://example.com'/><button onclick='runScan()'>Run Report</button>
<div id='out'></div>
<script>
async function runScan(){
  const url=document.getElementById('url').value;
  const out=document.getElementById('out');
  out.innerHTML='<p>Scanning...</p>';
  const res=await fetch('/api/scan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
  const data=await res.json();
  if(!res.ok){out.innerHTML='<div class="card"><b>Error:</b> '+data.error+'</div>'; return;}
  out.innerHTML=`<div class='card'><h2>Score: ${data.seo_score}/100</h2><p><b>Status:</b> ${data.http_status}</p><p><b>Issues:</b></p><ul>${data.issues.map(i=>`<li>${i}</li>`).join('')}</ul></div>
  <div class='card'><h3>Opportunities / Fixes</h3><ul>${data.recommendations.map(r=>`<li><b>${r.opportunity}</b> (${r.priority})<br/>${r.fix}</li>`).join('')}</ul></div>
  <div class='card'><h3>Keyword Opportunities</h3><p>${data.keyword_opportunities.join(', ')}</p></div>
  <div class='card'><h3>Raw JSON</h3><pre>${JSON.stringify(data,null,2)}</pre></div>`;
}
</script></body></html>"""

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype='application/json'):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/':
            self._send(200, HTML_PAGE.encode(), 'text/html; charset=utf-8')
            return
        if self.path == '/api/reports':
            conn = sqlite3.connect(DB_PATH)
            rows = conn.execute('SELECT id,url,created_at,report_json FROM reports ORDER BY id DESC LIMIT 20').fetchall()
            conn.close()
            payload = [{'id': r[0], 'url': r[1], 'created_at': r[2], 'report': json.loads(r[3])} for r in rows]
            self._send(200, json.dumps(payload).encode())
            return
        self._send(404, b'{"error":"Not found"}')

    def do_POST(self):
        if self.path != '/api/scan':
            self._send(404, b'{"error":"Not found"}')
            return
        length = int(self.headers.get('Content-Length', '0'))
        data = json.loads(self.rfile.read(length) or b'{}')
        url = data.get('url', '').strip()
        if not url.startswith('http'):
            self._send(400, b'{"error":"Please enter a valid http/https URL"}')
            return
        try:
            report = generate_report(url)
            conn = sqlite3.connect(DB_PATH)
            conn.execute('INSERT INTO reports(url,created_at,report_json) VALUES(?,?,?)',
                         (url, datetime.utcnow().isoformat() + 'Z', json.dumps(report)))
            conn.commit()
            conn.close()
            self._send(200, json.dumps(report).encode())
        except Exception as e:
            self._send(500, json.dumps({'error': str(e)}).encode())

if __name__ == '__main__':
    init_db()
    port = int(os.getenv('PORT', '3000'))
    print(f'SEO Dashboard running on http://0.0.0.0:{port}')
    HTTPServer(('0.0.0.0', port), Handler).serve_forever()
