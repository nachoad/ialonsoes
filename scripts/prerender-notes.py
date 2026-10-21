#!/usr/bin/env python3
"""Bake the rendered Notes list into notes/index.html as static HTML + JSON-LD.

The page builds its cards with JavaScript (static entries + Medium feed), which many
search and AI crawlers don't execute. This renders the page in headless Chrome and
writes the result between the prerender markers, so the content is in the raw HTML.
The page's own JS replaces it at load, so the visible behaviour doesn't change.

It runs daily from .github/workflows/prerender-notes.yml; to run it by hand:
  python3 scripts/prerender-notes.py
"""
import html, json, os, re, shutil, subprocess, sys, time, urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / 'notes' / 'index.html'
CHROME = (os.environ.get('CHROME') or shutil.which('google-chrome') or shutil.which('chromium')
          or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
PORT = 8766
FEED = 'https://medium.com/feed/@nachoad'
CONTENT = '{http://purl.org/rss/1.0/modules/content/}encoded'
EXCERPT_WORDS = 40  # keep in sync with notes/index.html


class Cards(HTMLParser):
    """Collects each rendered .note-card as a dict."""
    def __init__(self):
        super().__init__()
        self.cards, self.cur, self.field = [], None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get('class', '')
        if tag == 'article' and 'note-card' in cls:
            self.cur = {'category': a.get('data-category'), 'source': a.get('data-source'), 'year': a.get('data-year')}
        elif self.cur is not None:
            if tag == 'h3': self.field = 'title'
            elif tag == 'p' and 'note-excerpt' in cls: self.field = 'excerpt'
            elif tag == 'span' and cls == 'note-date': self.field = 'date'
            elif tag == 'a' and 'note-read' in cls: self.cur['url'] = a.get('href')

    def handle_data(self, data):
        if self.cur is not None and self.field:
            self.cur[self.field] = self.cur.get(self.field, '') + data

    def handle_endtag(self, tag):
        if self.field and tag in ('h3', 'p', 'span'): self.field = None
        if tag == 'article' and self.cur is not None:
            self.cards.append(self.cur); self.cur = None


class Text(HTMLParser):
    """Plain text of an article's HTML, skipping headings, figures, images, scripts and styles."""
    SKIP = {'h1', 'h2', 'h3', 'figure', 'script', 'style'}
    BLOCK = {'p', 'li', 'blockquote', 'pre', 'br', 'h4', 'h5', 'h6'}  # the feed has no whitespace between these

    def __init__(self):
        super().__init__()
        self.depth, self.parts = 0, []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP: self.depth += 1
        if tag in self.BLOCK: self.parts.append(' ')

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.depth: self.depth -= 1
        if tag in self.BLOCK: self.parts.append(' ')

    def handle_data(self, data):
        if not self.depth: self.parts.append(data)


def excerpt(content):
    t = Text(); t.feed(content or '')
    words = ''.join(t.parts).split()
    return ' '.join(words[:EXCERPT_WORDS]) + ('…' if len(words) > EXCERPT_WORDS else '')


def medium_items():
    """Medium articles as the page's minimal JSON, fetched here so visitors don't wait on a third-party API."""
    req = urllib.request.Request(FEED, headers={'User-Agent': 'ialonso.es prerender'})
    items = ET.parse(urllib.request.urlopen(req, timeout=30)).findall('channel/item')
    if not items:
        sys.exit('Medium feed returned no items. Not writing.')
    return [{'title': i.findtext('title'), 'url': i.findtext('link').split('?source=')[0],
             'date': parsedate_to_datetime(i.findtext('pubDate')).strftime('%Y-%m-%d'),
             'excerpt': excerpt(i.findtext(CONTENT) or i.findtext('description'))} for i in items]


def main():
    src = PAGE.read_text()
    data = json.dumps(medium_items(), ensure_ascii=False, indent=2).replace('</', '<\\/')
    src = re.sub(r'(<!-- prerender:medium -->).*?(<!-- /prerender:medium -->)',
                 lambda m: f'{m.group(1)}\n  <script type="application/json" id="mediumData">{data}</script>\n  {m.group(2)}', src, flags=re.S)
    PAGE.write_text(src)

    server = subprocess.Popen([sys.executable, '-m', 'http.server', str(PORT)], cwd=ROOT,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    try:
        dom = subprocess.run([CHROME, '--headless', '--disable-gpu', '--no-sandbox', '--virtual-time-budget=8000', '--dump-dom',
                              f'http://localhost:{PORT}/notes/'], capture_output=True, text=True, check=True).stdout
    finally:
        server.terminate()

    parser = Cards(); parser.feed(dom)
    cards = parser.cards
    for c in cards:
        c['url'] = c['url'].split('?source=')[0]  # drop Medium's RSS tracking param
    if len(cards) < 10:
        sys.exit(f'Only {len(cards)} cards rendered; Medium feed probably failed. Not writing.')

    esc = html.escape
    static = '\n'.join(
        '        <article class="note-card">'
        f'<h3 class="note-title"><a href="{esc(c["url"])}">{esc(c["title"])}</a></h3>'
        f'<p class="note-meta">{esc(c["category"])} · {esc(c["source"])} · {esc(c["date"])}</p>'
        f'<p class="note-excerpt text-secondary">{esc(c["excerpt"].strip())}</p></article>'
        for c in cards)

    items = [{'@type': 'ListItem', 'position': i + 1, 'url': c['url'], 'name': c['title']} for i, c in enumerate(cards)]
    ld = {'@context': 'https://schema.org', '@type': 'CollectionPage', 'url': 'https://ialonso.es/notes/',
          'name': 'Notes by Ignacio Alonso Delgado', 'author': {'@id': 'https://ialonso.es/#person'},
          'mainEntity': {'@type': 'ItemList', 'itemListElement': items}}
    ld_html = '<script type="application/ld+json">\n' + json.dumps(ld, ensure_ascii=False, indent=2) + '\n  </script>'

    src = PAGE.read_text()
    src = re.sub(r'(<!-- prerender:list -->).*?(<!-- /prerender:list -->)',
                 lambda m: f'{m.group(1)}\n{static}\n        {m.group(2)}', src, flags=re.S)
    src = re.sub(r'(<!-- prerender:ld -->).*?(<!-- /prerender:ld -->)',
                 lambda m: f'{m.group(1)}\n  {ld_html}\n  {m.group(2)}', src, flags=re.S)
    PAGE.write_text(src)
    print(f'Wrote {len(cards)} entries')


main()
