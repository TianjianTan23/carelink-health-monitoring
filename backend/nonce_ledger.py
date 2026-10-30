"""Existing-only replay ledger. Initialization is a separate operator action.

No runtime path creates a ledger, repairs a marker, chmods files, or migrates a
legacy schema. The v2 identity detects mismatched pairs, not coordinated rollback
of an entire backup: history continuity still requires an approved recovery plan.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import sqlite3
import stat
import time

from .device_auth_errors import DeviceAuthError

FORMAT = 2
AUTHORIZATION = "CREATE A NEW INSTALLATION LEDGER"
UNAVAILABLE = "Device authentication unavailable"
SCHEMA = {
    "device_nonces": """CREATE TABLE device_nonces (
        device_id TEXT NOT NULL, nonce TEXT NOT NULL, signed_at INTEGER NOT NULL,
        accepted_at INTEGER NOT NULL, PRIMARY KEY(device_id, nonce)
    ) WITHOUT ROWID""",
    "nonce_metadata": """CREATE TABLE nonce_metadata (
        singleton INTEGER PRIMARY KEY CHECK(singleton=1),
        format INTEGER NOT NULL CHECK(format=2), ledger_id TEXT NOT NULL,
        admissions INTEGER NOT NULL CHECK(admissions>=0)
    )""",
    "nonce_count": """CREATE TRIGGER nonce_count AFTER INSERT ON device_nonces
        BEGIN UPDATE nonce_metadata SET admissions=admissions+1 WHERE singleton=1; END""",
    "nonce_no_delete": """CREATE TRIGGER nonce_no_delete BEFORE DELETE ON device_nonces
        BEGIN SELECT RAISE(ABORT, 'Append only ledger'); END""",
    "nonce_no_update": """CREATE TRIGGER nonce_no_update BEFORE UPDATE ON device_nonces
        BEGIN SELECT RAISE(ABORT, 'Append only ledger'); END""",
}


def _fail():
    raise DeviceAuthError(503, UNAVAILABLE)


def _directory(path):
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) & 0o077 or info.st_mode & 0o700 != 0o700
            or not os.access(path, os.R_OK | os.W_OK | os.X_OK)):
        _fail()


def _file(path):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077
            or info.st_mode & 0o600 != 0o600):
        _fail()
    # NEVER independently open/close a SQLite main/WAL/SHM descriptor here.
    # POSIX record locks are process-associated; an unrelated close can release
    # locks held by another SQLite connection/thread in the same process.
    # Non-invasive ACL/mode/flags checks + SQLite mode=rw, BEGIN IMMEDIATE and
    # the actual FULL commit enforce writability without invalidating its locks.
    immutable=getattr(stat,"UF_IMMUTABLE",0)|getattr(stat,"SF_IMMUTABLE",0)
    if getattr(info,"st_flags",0)&immutable:
        _fail()
    if not os.access(path,os.R_OK|os.W_OK):
        # access() reports False for ENOENT as well as ACL denial. SQLite may
        # unlink an idle WAL/SHM between lstat and this probe. Preserve ENOENT
        # so ONLY the existing sidecar-specific handler can accept absence;
        # main/marker disappearance still fails closed in connect(). A present
        # inaccessible file remains a hard failure; never open/close a DB fd.
        path.lstat()
        _fail()
    return info


def _exists(path):
    # Unlike exists(), dangling symlinks are evidence, never an empty target.
    return os.path.lexists(path)


def _fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class NonceCursor(sqlite3.Cursor):
    def execute(self,*args,**kwargs):self.connection.require_lease();return super().execute(*args,**kwargs)
    def executemany(self,*args,**kwargs):self.connection.require_lease();return super().executemany(*args,**kwargs)
    def executescript(self,*args,**kwargs):self.connection.require_lease();return super().executescript(*args,**kwargs)


class NonceConnection(sqlite3.Connection):
    _bound_path=None
    def bind_lease(self,path):self._bound_path=path
    def require_lease(self):
        if self._bound_path is None:return
        from .write_gate import CURRENT
        lease=CURRENT.get()
        if not lease or not lease['valid'] or lease['path']!=self._bound_path:_fail()
    def cursor(self,*args,**kwargs):
        if args or kwargs:_fail()
        return super().cursor(factory=NonceCursor)
    def execute(self,*args,**kwargs):return self.cursor().execute(*args,**kwargs)
    def executemany(self,*args,**kwargs):return self.cursor().executemany(*args,**kwargs)
    def executescript(self,*args,**kwargs):return self.cursor().executescript(*args,**kwargs)
    def commit(self):
        if self.total_changes:self.require_lease()
        return super().commit()


def _sqlite(path):
    # mode=rw deliberately disallows SQLite's implicit CREATE behavior.
    return sqlite3.connect(path.absolute().as_uri() + "?mode=rw", uri=True, timeout=15,factory=NonceConnection)


def initialize_new_ledger(path: Path, *, authorization: str) -> None:
    """Explicit NEW installation only, never recovery, upgrade or reset.

    A durable exclusive intent file serializes initialization. Any interruption
    leaves evidence and blocks runtime/another initialization; no automatic retry
    or cleanup is allowed. Publish the marker only after the DB is committed and
    synced. Remove the intent only after both files and directory are durable.
    """
    if authorization != AUTHORIZATION:
        _fail()
    path = Path(path).absolute()
    marker = path.with_name(path.name + ".initialized")
    intent = path.with_name(path.name + ".initializing")
    try:
        _directory(path.parent)
        # Refuse all pre-existing artifacts, including WAL/SHM/journal remnants.
        artifacts = (path, marker, intent, *(path.with_name(path.name+s) for s in ("-wal", "-shm", "-journal", ".control")))
        if any(_exists(p) for p in artifacts):
            _fail()
        fd = os.open(intent, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(b"CareLink new-installation intent v2\n")
            stream.flush()
            os.fsync(stream.fileno())
        _fsync_directory(path.parent)
        # Once the intent exists, do not remove ANY evidence on failure.
        if any(_exists(p) for p in artifacts if p != intent):
            _fail()
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        ledger_id = secrets.token_hex(16)
        db = _sqlite(path)
        try:
            db.execute("PRAGMA synchronous=FULL")
            # DELETE during creation avoids uncheckpointed initial schema WAL.
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("BEGIN IMMEDIATE")
            for sql in SCHEMA.values():
                db.execute(sql)
            db.execute("INSERT INTO nonce_metadata VALUES (1, ?, ?, 0)", (FORMAT, ledger_id))
            db.execute("PRAGMA user_version=2")
            db.commit()
            if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                _fail()
            if db.execute("PRAGMA journal_mode=WAL").fetchone() != ("wal",):
                _fail()
        finally:
            db.close()
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump({"format": FORMAT, "ledger_id": ledger_id}, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        _fsync_directory(path.parent)
        intent.unlink()
        _fsync_directory(path.parent)
    except (OSError, sqlite3.Error, ValueError):
        raise DeviceAuthError(503, UNAVAILABLE) from None


class NonceStore:
    """Open an existing v2 pair only; UNIQUE + FULL transaction has one winner.

    Reservations remain consumed even if ingestion subsequently fails. Never
    prune or reset history. All structural checks run under the write transaction
    so concurrent workers observe the same committed metadata and rows.
    """
    def __init__(self, path: Path):
        self.path = Path(path).absolute()
        self.marker = self.path.with_name(self.path.name + ".initialized")
        self.intent = self.path.with_name(self.path.name + ".initializing")
        self.ledger_id = None
        self.file_identity = None
        with self.connect(full_check=True):
            pass

    def _paths(self):
        _directory(self.path.parent)
        if _exists(self.intent):
            _fail()
        info = _file(self.path)
        if info.st_size < 512:
            _fail()
        identity = (info.st_dev, info.st_ino)
        if self.file_identity is not None and self.file_identity != identity:
            _fail()
        _file(self.marker)
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = self.path.with_name(self.path.name + suffix)
            if _exists(sidecar):
                try:
                    _file(sidecar)
                except FileNotFoundError:
                    pass  # SQLite legitimately unlinks idle sidecars.
        # Open without following a replacement symlink; bound size and strict
        # canonical encoding reject truncated/duplicate-key/legacy markers.
        fd = os.open(self.marker, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            data = stream.read(513)
            after = self.marker.lstat()
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino) or len(data) > 512:
            _fail()
        marker = json.loads(data)
        if (not isinstance(marker, dict) or set(marker) != {"format", "ledger_id"}
                or type(marker["format"]) is not int or marker["format"] != FORMAT
                or not isinstance(marker["ledger_id"], str) or len(marker["ledger_id"]) != 32
                or any(c not in "0123456789abcdef" for c in marker["ledger_id"])):
            _fail()
        if data != (json.dumps(marker, sort_keys=True) + "\n").encode():
            _fail()
        if self.ledger_id is not None and marker["ledger_id"] != self.ledger_id:
            _fail()
        return marker["ledger_id"], identity

    def _validate(self, db, ledger_id, full_check):
        if db.execute("PRAGMA user_version").fetchone() != (FORMAT,):
            _fail()
        if db.execute("PRAGMA journal_mode").fetchone() != ("wal",):
            _fail()
        actual = dict(db.execute("SELECT name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"))
        if actual != SCHEMA:
            _fail()
        meta = db.execute("SELECT singleton, format, ledger_id, admissions FROM nonce_metadata").fetchall()
        count = db.execute("SELECT count(*) FROM device_nonces").fetchone()[0]
        if meta != [(1, FORMAT, ledger_id, count)]:
            _fail()
        if full_check and db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            _fail()

    @contextmanager
    def connect(self, *, full_check=True):
        db = None
        try:
            ledger_id, identity = self._paths()
            db = _sqlite(self.path)
            db.execute("PRAGMA busy_timeout=15000")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA trusted_schema=OFF")
            db.execute("BEGIN IMMEDIATE")
            # Catch removal/replacement between checking paths and opening DB.
            if self._paths() != (ledger_id, identity):
                _fail()
            self._validate(db, ledger_id, full_check)
            self.ledger_id, self.file_identity = ledger_id, identity
            # Bound ledgers may be inspected without a lease, but mutation via
            # the low-level connection must not bypass unified admission.
            binding=self.path.with_name(self.path.name+'.control')
            if _exists(binding):
                db.bind_lease(self.path)
                from .write_gate import CURRENT
                mutations={sqlite3.SQLITE_INSERT,sqlite3.SQLITE_UPDATE,sqlite3.SQLITE_DELETE,
                    sqlite3.SQLITE_CREATE_TABLE,sqlite3.SQLITE_DROP_TABLE,sqlite3.SQLITE_ALTER_TABLE}
                def authorize(action,*args):
                    lease=CURRENT.get()
                    if action in mutations and not (lease and lease['valid'] and lease['path']==self.path):
                        return sqlite3.SQLITE_DENY
                    return sqlite3.SQLITE_OK
                db.set_authorizer(authorize)
            yield db
            if self._paths() != (ledger_id, identity):
                _fail()
            db.commit()
        except (OSError, sqlite3.Error, ValueError, TypeError):
            raise DeviceAuthError(503, UNAVAILABLE) from None
        finally:
            if db is not None:
                try:
                    db.close()  # Roll back uncommitted work, including interruption.
                except sqlite3.Error:
                    raise DeviceAuthError(503, UNAVAILABLE) from None

    def reserve(self, device: str, nonce: str, signed_at: int, now: int) -> None:
        binding=self.path.with_name(self.path.name+'.control')
        if _exists(binding):
            from .write_gate import CURRENT,write_lease
            from .ledger_control import Controller,read_json,ControlError
            lease=CURRENT.get()
            if not (lease and lease['valid'] and lease['path']==self.path):
                try:
                    with write_lease(Controller(read_json(binding)['control_root'])) as selected:
                        if selected!=self.path:_fail()
                        return self._reserve(device,nonce,signed_at,now)
                except ControlError:
                    raise DeviceAuthError(503,UNAVAILABLE) from None
        return self._reserve(device,nonce,signed_at,now)

    def _reserve(self, device: str, nonce: str, signed_at: int, now: int) -> None:
        with self.connect() as db:
            now = int(time.time())  # Recheck freshness after waiting for the lock.
            if abs(now - signed_at) > 60:
                raise DeviceAuthError(401, "Device authentication failed")
            try:
                db.execute("INSERT INTO device_nonces VALUES (?, ?, ?, ?)", (device, nonce, signed_at, now))
            except sqlite3.IntegrityError:
                # Only an already committed primary key is a replay; other
                # integrity failures are unavailable storage, never a success.
                if db.execute("SELECT 1 FROM device_nonces WHERE device_id=? AND nonce=?", (device, nonce)).fetchone():
                    raise DeviceAuthError(409, "Device request replay rejected") from None
                _fail()
