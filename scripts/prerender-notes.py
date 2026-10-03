#!/usr/bin/env python3
"""Bake the rendered Notes list into notes/index.html as static HTML + JSON-LD.

The page builds its cards with JavaScript (static entries + Medium feed), which many
search and AI crawlers don't execute. This renders the page in headless Chrome and
writes the result between the prerender markers, so the content is in the raw HTML.
The page's own JS replaces it at load, so the visible behaviour doesn't change.

It runs daily from .github/workflows/prerender-notes.yml; to run it by hand:
  python3 scripts/prerender-notes.py
"""
import html, json, os, re, shutil, subprocess, sys, time
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / 'notes' / 'index.html'
CHROME = (os.environ.get('CHROME') or shutil.which('google-chrome') or shutil.which('chromium')
          or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
PORT = 8766


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


def main():
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
