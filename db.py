import sqlite3, threading, datetime, time, os
from pathlib import Path
from config import DB_PATH, DEFAULT_ENGINE, DEFAULT_LEVEL

Path(DB_PATH).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
_l = threading.RLock()
_c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
try:
    os.chmod(DB_PATH, 0o600)
except OSError:
    pass
_c.execute("PRAGMA journal_mode=WAL")
_c.execute("PRAGMA foreign_keys=ON")
_c.row_factory = sqlite3.Row
_c.executescript("""
CREATE TABLE IF NOT EXISTS groups(chat_id INTEGER PRIMARY KEY, title TEXT, kind TEXT DEFAULT 'group',
 enabled INT DEFAULT 1, engine TEXT DEFAULT 'smart', level TEXT DEFAULT 'mid', warn_limit INT DEFAULT 3,
 punish TEXT DEFAULT 'mute', s_photo INT DEFAULT 1, s_video INT DEFAULT 1, s_gif INT DEFAULT 1,
 s_sticker INT DEFAULT 1, s_note INT DEFAULT 1, textfilter INT DEFAULT 1, s_ai INT DEFAULT 1,
 admin_mode TEXT DEFAULT 'skip', chan_mode TEXT DEFAULT 'delete', notify INT DEFAULT 0, deleted INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS words(w TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS packs(n TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS warns(chat_id INT, user_id INT, n INT, PRIMARY KEY(chat_id, user_id));
CREATE TABLE IF NOT EXISTS seen(k TEXT PRIMARY KEY, bad INT, reason TEXT, why TEXT, ts INT);
""")
# migrate older installs
_cols = {r["name"] for r in _c.execute("PRAGMA table_info(groups)")}
for _n, _d in [("kind", "TEXT DEFAULT 'group'"), ("s_ai", "INT DEFAULT 1"),
               ("admin_mode", "TEXT DEFAULT 'skip'"), ("chan_mode", "TEXT DEFAULT 'delete'"),
               ("notify", "INT DEFAULT 0")]:
    if _n not in _cols:
        _c.execute(f"ALTER TABLE groups ADD COLUMN {_n} {_d}")
_c.execute("DELETE FROM seen WHERE ts<?", (int(time.time()) - 30 * 86400,))
_c.commit()

FIELDS = {"enabled", "engine", "level", "warn_limit", "punish", "s_photo", "s_video", "s_gif",
          "s_sticker", "s_note", "textfilter", "s_ai", "admin_mode", "chan_mode", "notify"}


def q(sql, a=(), w=False):
    with _l:
        r = _c.execute(sql, a).fetchall()
        if w:
            _c.commit()
        return r


def group(cid, title=None, kind="group"):
    r = q("SELECT * FROM groups WHERE chat_id=?", (cid,))
    if not r:
        q("INSERT INTO groups(chat_id,title,kind,engine,level) VALUES(?,?,?,?,?)",
          (cid, title or str(cid), kind, DEFAULT_ENGINE, DEFAULT_LEVEL), True)
    elif title and (r[0]["title"] != title or r[0]["kind"] != kind):
        q("UPDATE groups SET title=?,kind=? WHERE chat_id=?", (title, kind, cid), True)
    return q("SELECT * FROM groups WHERE chat_id=?", (cid,))[0]


def groups():
    return q("SELECT * FROM groups ORDER BY title")


def setg(cid, f, v):
    assert f in FIELDS
    q(f"UPDATE groups SET {f}=? WHERE chat_id=?", (v, cid), True)


def toggle(cid, f):
    setg(cid, f, 0 if group(cid)[f] else 1)


def inc_deleted(cid):
    q("UPDATE groups SET deleted=deleted+1 WHERE chat_id=?", (cid,), True)


def add_warn(cid, uid):
    q("INSERT INTO warns VALUES(?,?,1) ON CONFLICT(chat_id,user_id) DO UPDATE SET n=n+1", (cid, uid), True)
    return q("SELECT n FROM warns WHERE chat_id=? AND user_id=?", (cid, uid))[0]["n"]


def reset_warns(cid, uid=None):
    if uid:
        q("DELETE FROM warns WHERE chat_id=? AND user_id=?", (cid, uid), True)
    else:
        q("DELETE FROM warns WHERE chat_id=?", (cid,), True)


def get(k, d=None):
    r = q("SELECT v FROM kv WHERE k=?", (k,))
    return r[0]["v"] if r else d


def put(k, v):
    if v is None:
        q("DELETE FROM kv WHERE k=?", (k,), True)
    else:
        q("INSERT INTO kv VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)), True)


def usage(name):
    return int(get(f"{name}:{datetime.date.today().isoformat()}", "0"))


def usage_add(name, n=1):
    put(f"{name}:{datetime.date.today().isoformat()}", usage(name) + n)


def seen_get(k):
    r = q("SELECT * FROM seen WHERE k=?", (k,))
    return r[0] if r else None


def seen_put(k, bad, reason="", why=""):
    q("INSERT OR REPLACE INTO seen VALUES(?,?,?,?,?)", (k, int(bad), reason, why, int(time.time())), True)


def words():
    return {r["w"] for r in q("SELECT w FROM words")}


def packs():
    return {r["n"] for r in q("SELECT n FROM packs")}


def add(table, v):
    if table not in {"words", "packs"}:
        raise ValueError("unsupported table")
    q(f"INSERT OR IGNORE INTO {table}({'w' if table == 'words' else 'n'}) VALUES(?)", (v,), True)


def rem(table, v):
    if table not in {"words", "packs"}:
        raise ValueError("unsupported table")
    q(f"DELETE FROM {table} WHERE {'w' if table == 'words' else 'n'}=?", (v,), True)


def clear(table):
    if table not in {"words", "packs", "seen", "warns"}:
        raise ValueError("unsupported table")
    q(f"DELETE FROM {table}", (), True)
