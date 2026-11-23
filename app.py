"""A local Secret Santa exchange. Run with python3 app.py."""
import argparse
import hashlib
import hmac
import html
import secrets
import sqlite3
import time
import unicodedata
from contextlib import closing
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent
ADMIN = "mihaigirnita"
ADMIN_HASH = "474c01d3bfc2fe01f6087ebfe255704b:de7dd0f099b4f60a9bdfbaf0ad1bf5578de01099aebdfd7043172e97e48de3e2"
rng = secrets.SystemRandom()
esc = html.escape


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 300000).hex()


def draw(ids):
    recipients = ids.copy()
    while True:
        rng.shuffle(recipients)
        if all(a != b for a, b in zip(ids, recipients)):
            return list(zip(recipients, ids))


def page(content, signed_in=False):
    action = '<form method="post" action="/logout"><button class="quiet">Sign out</button></form>' if signed_in else ''
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Secret Santa · North Pole Post</title><link rel="stylesheet" href="/style.css"></head><body><header><div class="brand"><span class="mark" aria-hidden="true">✳</span> North Pole Post</div>{action}</header><main>{content}</main><footer><span aria-hidden="true">✦</span> North Pole Post <span aria-hidden="true">✦</span></footer></body></html>'''


def login(error=''):
    return page(f'''<div class="parcel"><section class="poster"><div class="stars" aria-hidden="true">✦　✧　✦</div><h1>Secret<br><i>Santa</i></h1><canvas id="scene" width="680" height="360" aria-hidden="true"></canvas><script src="/scene.js" defer></script></section><section class="login"><div class="smallstar" aria-hidden="true">✳</div><h2>Welcome, Santa.</h2><p>Sign in with the details from your organizer to find your gift recipient.</p>{error}<form method="post" action="/login"><label>Username<input required name="username" autocomplete="username" autocapitalize="none" spellcheck="false" placeholder="Your username"></label><label>Password<input required name="password" type="password" autocomplete="current-password" placeholder="Your password"></label><button>Sign in</button></form><p class="note">Organizing the exchange? Use your admin login here.</p></section></div>''')


def panel(title, body):
    return page(f'<section class="card"><div class="smallstar" aria-hidden="true">✳</div><h1>{esc(title)}</h1>{body}</section>', True)


def notice(message):
    return f'<div role="alert" class="notice">{esc(message)}</div>'


class Handler(BaseHTTPRequestHandler):
    def reply(self, body, status=200, mime='text/html; charset=utf-8', headers=()):
        payload = body.encode()
        self.send_response(status)
        for key, value in headers:
            self.send_header(key, value)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'")
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def redirect(self, cookie=None):
        headers = [('Location', '/')]
        if cookie is not None:
            headers.append(('Set-Cookie', 'santa=' + cookie + '; Path=/; HttpOnly; SameSite=Strict'))
        self.reply('', 303, headers=headers)

    def session(self, db):
        cookie = SimpleCookie()
        cookie.load(self.headers.get('Cookie', ''))
        key = cookie.get('santa')
        if key:
            return db.execute('SELECT * FROM sessions WHERE token=? AND expires>?', (key.value, time.time())).fetchone()

    def dashboard(self, db, message=''):
        event = db.execute('SELECT * FROM events ORDER BY id DESC LIMIT 1').fetchone()
        create = '<form method="post" action="/create"><label>Exchange name<input name="name" required maxlength="80" placeholder="Family Christmas"></label><button>Create exchange</button></form>'
        if not event:
            return panel('Start a Secret Santa', message + create)
        members = db.execute('SELECT name,username FROM people WHERE event=? ORDER BY id', (event['id'],)).fetchall()
        rows = ''.join(f'<li><strong>{esc(m["name"])}</strong><small>{esc(m["username"])}</small></li>' for m in members)
        roster = f'<h2>Participants ({len(members)})</h2><ul>{rows}</ul>'
        event_id = f'<input type="hidden" name="event" value="{event["id"]}">'
        if event['done']:
            content = '<p>The draw is ready. Each participant can sign in to see their recipient.</p>' + roster + '<details><summary>Start another exchange</summary>' + create + '</details>'
        else:
            disabled = ' disabled' if len(members) < 2 else ''
            content = f'<form method="post" action="/add">{event_id}<label>Participant name<input name="name" required maxlength="80" placeholder="Full name"></label><button>Add participant</button></form>{roster}<p>Finish adding everyone before drawing names. The draw is final and needs at least two participants.</p><form method="post" action="/draw">{event_id}<button{disabled}>Draw names</button></form>'
        return panel(event['name'], message + content)

    def do_GET(self):
        path = urlsplit(self.path).path
        assets = {'/style.css': 'text/css', '/scene.js': 'application/javascript'}
        if path in assets:
            return self.reply((ROOT / path[1:]).read_text(), mime=assets[path])
        if path != '/':
            return self.reply('Page not found', 404)
        with closing(connect()) as db:
            session = self.session(db)
            if not session:
                return self.reply(login())
            if session['person'] == 0:
                return self.reply(self.dashboard(db))
            row = db.execute('SELECT p.name,e.name exchange,r.name recipient FROM people p JOIN events e ON e.id=p.event LEFT JOIN people r ON r.id=p.recipient WHERE p.id=?', (session['person'],)).fetchone()
            body = f'<p>Hello, {esc(row["name"])}.</p>'
            if row['recipient'] is None:
                body += '<p>Your organizer is still preparing the draw. Check back here once names have been drawn.</p><a href="/">Check again</a>'
            else:
                body += f'<p>Your gift recipient is</p><div class="recipient">{esc(row["recipient"])}</div>'
            self.reply(panel(row['exchange'], body))

    def do_POST(self):
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + self.headers.get('Host', ''):
            return self.reply('Invalid origin', 403)
        try:
            size = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            return self.reply('Invalid request', 400)
        if not 0 <= size <= 8192:
            return self.reply('Request too large', 413)
        fields = parse_qs(self.rfile.read(size).decode('utf-8', 'replace'))
        def field(key):
            return fields.get(key, [''])[0]
        with closing(connect()) as db, db:
            session = self.session(db)
            if self.path == '/login':
                username = field('username').strip().lower()
                row = db.execute('SELECT id,hash FROM people WHERE username=?', (username,)).fetchone()
                stored = row['hash'] if row else ADMIN_HASH
                salt, digest = stored.split(':')
                valid = hmac.compare_digest(digest, password_hash(field('password'), salt))
                if not valid or (not row and username != ADMIN):
                    return self.reply(login(notice('Check your username and password and try again.')), 401)
                token = secrets.token_urlsafe(32)
                db.execute('DELETE FROM sessions WHERE expires<=?', (time.time(),))
                db.execute('INSERT INTO sessions VALUES(?,?,?)', (token, row['id'] if row else 0, time.time()+43200))
                db.commit()
                return self.redirect(token)
            if not session:
                return self.redirect()
            if self.path == '/logout':
                db.execute('DELETE FROM sessions WHERE token=?', (session['token'],))
                db.commit()
                return self.redirect('')
            if session['person'] != 0:
                return self.reply('Admin access required', 403)
            db.execute('BEGIN IMMEDIATE')
            event = db.execute('SELECT * FROM events ORDER BY id DESC LIMIT 1').fetchone()
            name = field('name').strip()
            if self.path in ('/add', '/create') and not 1 <= len(name) <= 80:
                return self.reply(self.dashboard(db, notice('Enter a name of 1 to 80 characters.')), 400)
            if self.path == '/create' and (not event or event['done']):
                db.execute('INSERT INTO events(name) VALUES(?)', (name,))
            elif not event or str(event['id']) != field('event') or event['done']:
                return self.reply(self.dashboard(db, notice('This form is out of date. Check the current exchange below.')), 409)
            elif self.path == '/add':
                existing = db.execute('SELECT name FROM people WHERE event=?', (event['id'],))
                if any(r['name'].casefold() == name.casefold() for r in existing):
                    return self.reply(self.dashboard(db, notice('That name is already on the list. Add a surname or initial to distinguish two people.')), 409)
                base = ''.join(c for c in unicodedata.normalize('NFKD', name).lower() if c.isascii() and c.isalnum())[:18] or 'santa'
                username = base + '-' + secrets.token_hex(4)
                while db.execute('SELECT 1 FROM people WHERE username=?', (username,)).fetchone():
                    username = base + '-' + secrets.token_hex(4)
                password = secrets.token_urlsafe(12)
                salt = secrets.token_hex(16)
                db.execute('INSERT INTO people(event,name,username,hash) VALUES(?,?,?,?)', (event['id'], name, username, salt+':'+password_hash(password,salt)))
                db.commit()
                return self.reply(panel('Login ready', f'<p>Share these details privately with <strong>{esc(name)}</strong>. The password is shown once.</p><dl><dt>Username</dt><dd>{username}</dd><dt>Password</dt><dd>{password}</dd></dl><a class="button" href="/">Back to exchange</a>'))
            elif self.path == '/draw':
                ids = [r[0] for r in db.execute('SELECT id FROM people WHERE event=?', (event['id'],))]
                if len(ids) < 2:
                    return self.reply(self.dashboard(db, notice('Add at least two participants first.')), 400)
                db.executemany('UPDATE people SET recipient=? WHERE id=?', draw(ids))
                db.execute('UPDATE events SET done=1 WHERE id=?', (event['id'],))
            else:
                return self.reply('Page not found', 404)
            db.commit()
            self.redirect()


def connect():
    db = sqlite3.connect(DB, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db


if __name__ == '__main__':
    import os
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--database', default=str(ROOT / 'santa.sqlite3'))
    args = parser.parse_args()
    DB = args.database
    with closing(connect()) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, name TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS people(id INTEGER PRIMARY KEY, event INTEGER NOT NULL REFERENCES events(id),
            name TEXT NOT NULL, username TEXT NOT NULL UNIQUE, hash TEXT NOT NULL,
            recipient INTEGER UNIQUE REFERENCES people(id), CHECK(recipient != id));
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, person INTEGER NOT NULL, expires REAL NOT NULL);
        """)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f'Listening on http://{args.host}:{server.server_port}', flush=True)
    server.serve_forever()
