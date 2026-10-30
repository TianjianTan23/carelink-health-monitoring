"""Explicit offline migration and cooperative whole-request admission gate.

Never discovers, initializes or repairs a missing control/ledger. Operator writer
inventory is a REQUIRED trust input, not OS proof that unknown writers are absent.
All managed receivers must use this gate; legacy processes must first be stopped
under a separately authorized maintenance plan. No automatic production adoption.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
import stat
import subprocess
import sys

from .nonce_ledger import NonceStore, SCHEMA, _file, _directory, _fsync_directory
from .device_auth_errors import DeviceAuthError


class ControlError(Exception):
    pass


def refuse():
    raise ControlError("Ledger control unavailable; preserve evidence")


def read_json(path):
    _file(path)
    if path.stat().st_size > 65536: refuse()
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:refuse()
            result[key]=value
        return result
    with path.open() as stream:return json.load(stream,object_pairs_hook=unique)


def private_new(path, data):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())


def atomic_json(path, data):
    # A failed temporary write is retained as diagnostic evidence.
    temp = path.with_name(path.name+".pending-"+secrets.token_hex(8))
    private_new(temp, (json.dumps(data, sort_keys=True)+"\n").encode())
    os.replace(temp, path); _fsync_directory(path.parent)

def _require_sqlite_main_header(path: Path) -> None:
    """Inspect in a separate process: raw close must not release OUR locks.

    Even opening BEFORE a new SQLite connection is unsafe if another connection
    in this process holds a transaction on the same inode. The isolated helper
    never opens SQLite or inherits a database descriptor. A failed probe is not
    a repair attempt; caller keeps the gate frozen and preserves all artifacts.
    """
    code = r"""import os,stat,sys
fd=os.open(sys.argv[1],os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
try:
 a=os.fstat(fd); b=os.lstat(sys.argv[1]); header=os.read(fd,16)
 valid=(stat.S_ISREG(a.st_mode) and (a.st_dev,a.st_ino)==(b.st_dev,b.st_ino)
        and a.st_uid==os.getuid() and a.st_nlink==1 and not a.st_mode&0o077
        and header==b'SQLite format 3\x00')
finally:os.close(fd)
sys.exit(0 if valid else 1)
"""
    try:
        result = subprocess.run([sys.executable,"-I","-S","-c",code,str(path)],
            close_fds=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
        if result.returncode != 0: refuse()
    except (OSError,subprocess.TimeoutExpired):
        refuse()


def sql(path, mode="ro", *, allow_empty=False):
    """Open a validated SQLite database and close it on context exit.

    allow_empty is reserved for the explicitly created migration destination
    immediately before SQLite's backup API populates it.
    """
    path = Path(path)

    if mode not in {"ro", "rw"}:
        refuse()

    _directory(path.parent)
    _file(path)

    if allow_empty:
        # Only the explicit migration destination may start empty.
        if mode != "rw":
            refuse()

        try:
            if path.stat().st_size != 0:
                refuse()
        except OSError:
            refuse()
    else:
        # Crucially, check the main file BEFORE sqlite3.connect().
        # A WAL sidecar must not mask an invalid main-file header.
        _require_sqlite_main_header(path)

    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = path.with_name(path.name + suffix)

        if os.path.lexists(sidecar):
            # An empty destination must not inherit existing sidecars.
            if allow_empty:
                refuse()

            try:
                _file(sidecar)
            except FileNotFoundError:
                pass

    class ClosingConnection(sqlite3.Connection):
        def __exit__(self, *args):
            try:
                return super().__exit__(*args)
            finally:
                self.close()

    return sqlite3.connect(
        path.absolute().as_uri() + "?mode=" + mode,
        uri=True,
        timeout=2,
        factory=ClosingConnection,
    )


def require_independent_backup(source,backup):
    """Metadata-only identity check, before opening any SQLite connection."""
    try:
        if Path(source).resolve(strict=True)==Path(backup).resolve(strict=True) or os.path.samefile(source,backup):refuse()
    except (OSError,RuntimeError):
        refuse()


def history(db):
    result = db.execute("SELECT device_id,nonce,signed_at,accepted_at FROM device_nonces ORDER BY device_id,nonce").fetchall()
    for device, nonce, signed, accepted in result:
        if (not isinstance(device,str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}",device)
                or not isinstance(nonce,str) or not re.fullmatch(r"[0-9a-f]{32}",nonce)
                or type(signed) is not int or type(accepted) is not int or min(signed,accepted)<=0): refuse()
    return result


def fingerprint(rows):
    return {"count":len(rows), "digest":hashlib.sha256(json.dumps(rows,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()}

def validate(path, db):
    _directory(path.parent)
    _file(path)
    _require_sqlite_main_header(path)
    marker = path.with_name(path.name+".initialized"); _file(marker)
    if os.path.lexists(path.with_name(path.name+".initializing")): refuse()
    if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]: refuse()
    objects=dict(db.execute("SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"))
    version=db.execute("PRAGMA user_version").fetchone()[0]
    data=history(db)
    if version==0:
        if marker.read_bytes()!=b"CareLink persistent device nonce ledger v1\n" or set(objects)!={"device_nonces"}: refuse()
        columns=db.execute("PRAGMA table_info(device_nonces)").fetchall()
        if [(r[1],r[2],r[3],r[5]) for r in columns] != [("device_id","TEXT",1,1),("nonce","TEXT",1,2),("signed_at","INTEGER",1,0),("accepted_at","INTEGER",1,0)]: refuse()
        if "WITHOUT ROWID" not in objects["device_nonces"].upper(): refuse()
    elif version==2:
        m=read_json(marker)
        if objects!=SCHEMA or set(m)!={"format","ledger_id"} or m["format"]!=2: refuse()
        if marker.read_bytes()!=(json.dumps(m,sort_keys=True)+"\n").encode(): refuse()
        if db.execute("SELECT singleton,format,ledger_id,admissions FROM nonce_metadata").fetchall()!=[(1,2,m["ledger_id"],len(data))]: refuse()
    else: refuse()
    return version, data


class Controller:
    def __init__(self, root):
        self.root=Path(root).absolute()
        self.state_path=self.root/"state.json"; self.lock_path=self.root/"gate.lock"

    def binding(self,path, *, create=False):
        info=_file(self.lock_path)
        expected={"control_root":str(self.root),"gate":[info.st_dev,info.st_ino]}
        binding=path.with_name(path.name+".control")
        if create:private_new(binding,(json.dumps(expected,sort_keys=True)+"\n").encode())
        if read_json(binding)!=expected:refuse()

    @contextmanager
    def lock(self, *, shared=False, timeout=0):
        _directory(self.root); info=_file(self.lock_path)
        fd=os.open(self.lock_path,os.O_RDWR|os.O_NOFOLLOW)
        try:
            opened=os.fstat(fd)
            if (info.st_dev,info.st_ino)!=(opened.st_dev,opened.st_ino): refuse()
            # Requests reject immediately; administration also fails rather than
            # waiting indefinitely. Retry freeze after current requests drain.
            deadline=time.monotonic()+timeout
            while True:
                try:
                    fcntl.flock(fd,(fcntl.LOCK_SH if shared else fcntl.LOCK_EX)|fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic()>=deadline:refuse()
                    time.sleep(0.025)
            current=self.lock_path.lstat()
            if (current.st_dev,current.st_ino)!=(opened.st_dev,opened.st_ino): refuse()
            self.state()
            yield
        finally:
            fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)

    def state(self):
        data=read_json(self.state_path)
        if data.get("format")!=1 or data.get("phase") not in {"FROZEN","COPYING","VERIFIED","SWITCHED","ACTIVE"}: refuse()
        if type(data.get("sequence")) is not int or data["sequence"]<0:refuse()
        for name in ("gate.lock","admin.lock"):
            info=_file(self.root/name)
            if data["locks"].get(name)!=[info.st_dev,info.st_ino]:refuse()
        if data["sequence"]:
            event=read_json(self.root/data["event"])
            if event!={"sequence":data["sequence"],"phase":data["phase"],"at":data["changed_at"]}:refuse()
        receipt=Path(data["inventory"])
        _file(receipt)
        if hashlib.sha256(receipt.read_bytes()).hexdigest()!=data["inventory_digest"]: refuse()
        evidence=read_json(receipt)
        def allowed(value):
            p=Path(value)
            return p.is_absolute() and (str(p)==evidence["source"] or
                (p.name=="nonce.db" and p.parent.parent==self.root and re.fullmatch(r"[A-Za-z0-9_-]{1,64}",p.parent.name)))
        if not allowed(data["active"]) or (data.get("candidate") and not allowed(data["candidate"])):refuse()
        self.binding(Path(data["active"]))
        return data

    def save(self, state, phase, **updates):
        state={**state,**updates,"phase":phase,"sequence":state["sequence"]+1,"changed_at":int(time.time())}
        # Phase events contain no paths, row hashes, nonces or credentials.
        event=self.root/("event-%08d-%s.json"%(state["sequence"],secrets.token_hex(8)))
        private_new(event,(json.dumps({"sequence":state["sequence"],"phase":phase,"at":state["changed_at"]})+"\n").encode())
        state["event"]=event.name
        atomic_json(self.state_path,state)
        return state

    @classmethod
    def enroll(cls, root, source, inventory):
        """Explicit offline adoption only; inventory must be independently audited.

        No default paths and no production auto-detection. Source must match the
        exact approved identity AND complete logical checkpoint. Empty histories
        are refused for migration of a previously running installation.
        """
        root, source, inventory=map(lambda p:Path(p).absolute(),(root,source,inventory))
        evidence=read_json(inventory); _directory(root.parent)
        info=_file(source)
        if (evidence.get("all_writers_controlled") is not True or evidence.get("legacy_writers_stopped") is not True
                or not evidence.get("review_reference") or evidence.get("expires_at",0)<=time.time()
                or evidence.get("source")!=str(source) or evidence.get("device")!=info.st_dev or evidence.get("inode")!=info.st_ino): refuse()
        # Exclusive SQLite writer transaction also fences non-cooperating ledger
        # commits DURING capture. It is not a substitute for stopping old writers.
        with sql(source,"rw") as db:
            db.execute("BEGIN IMMEDIATE")
            version, rows=validate(source,db); checkpoint=fingerprint(rows)
            if not rows or evidence.get("checkpoint")!=checkpoint: refuse()
            root.mkdir(mode=0o700)  # Existing or partial enrollments never reset.
            private_new(root/"gate.lock",b"CareLink request gate v1\n")
            private_new(root/"admin.lock",b"CareLink administrator gate v1\n")
            cls(root).binding(source,create=True)
            private_new(root/"state.json",(json.dumps({"format":1,"sequence":0,"phase":"FROZEN","active":str(source),
                "checkpoint":checkpoint,"inventory":str(inventory),"inventory_digest":hashlib.sha256(inventory.read_bytes()).hexdigest(),
                "locks":{name:[(root/name).stat().st_dev,(root/name).stat().st_ino] for name in ("gate.lock","admin.lock")},
                "changed_at":int(time.time())},sort_keys=True)+"\n").encode())
            _fsync_directory(root)
        return cls(root)

    @contextmanager
    def admission(self):
        with self.lock(shared=True):
            s=self.state()
            if s["phase"]!="ACTIVE": refuse()
            target=Path(s["active"])
            NonceStore(target)
            yield target  # Caller MUST hold this through auth AND reading commit.

    def freeze(self, *, timeout=10):
        if not 0<=timeout<=30:refuse()
        # First persist FROZEN under a SH lock: existing SH requests may finish,
        # but every later admitted request sees FROZEN and rejects. Then drain.
        # Serialize the phase write with a separate administrative lock.
        with self.admin():
            with self.lock(shared=True):
                s=self.state()
                if s["phase"] not in {"ACTIVE","FROZEN"}: refuse()
                if s["phase"]=="ACTIVE":self.save(s,"FROZEN",checkpoint=None)
            with self.lock(timeout=timeout):
                s=self.state()
                with sql(Path(s["active"]),"rw") as db:
                    db.execute("BEGIN IMMEDIATE");_,rows=validate(Path(s["active"]),db)
                    if s.get("checkpoint") is not None and fingerprint(rows)!=s["checkpoint"]:refuse()
                    return self.save(s,"FROZEN",checkpoint=fingerprint(rows))

    @contextmanager
    def admin(self):
        # Created only at enrollment; no missing-lock auto repair.
        p=self.root/"admin.lock";_file(p)
        self.state()
        fd=os.open(p,os.O_RDWR|os.O_NOFOLLOW)
        try:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:refuse()
            yield
        finally:fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)

    def verify_backup(self,backup):
        """Compare ALL historical values against a drained authority, not count.

        This proves current equality only. It never establishes external backup
        provenance/freshness when the authoritative ledger is missing, and never
        restores or automatically resumes reception.
        """
        with self.admin(),self.lock():
            state=self.state()
            if state['phase']!='FROZEN' or state.get('checkpoint') is None:refuse()
            source=Path(state['active']);backup=Path(backup).absolute()
            require_independent_backup(source,backup)
            with sql(source,'rw') as current:
                current.execute('BEGIN IMMEDIATE');version,rows=validate(source,current)
                if version!=2 or fingerprint(rows)!=state['checkpoint']:refuse()
                with sql(backup) as copied:
                    copied_version,other=validate(backup,copied)
                if copied_version!=2 or rows!=other:refuse()
            return {'phase':state['phase'],'sequence':state['sequence'],'backup_records':len(rows)}

    def prepare(self, name, *, backup=None):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}",name):refuse()
        with self.admin(),self.lock():
            s=self.state()
            if s["phase"]!="FROZEN" or s.get("checkpoint") is None:refuse()
            source=Path(s["active"])
            if backup is not None:require_independent_backup(source,Path(backup).absolute())
            with sql(source,"rw") as src:
                src.execute("BEGIN IMMEDIATE");version,original=validate(source,src)
                if fingerprint(original)!=s["checkpoint"]:refuse()
                generation=self.root/name;generation.mkdir(mode=0o700)
                target=generation/"nonce.db"
                self.save(s,"COPYING",candidate=str(target))
                private_new(target.with_name(target.name+".initializing"),b"CareLink explicit migration in progress\n")
                # Backup from a separate RO connection: the writer lock above
                # prevents changes while this snapshot includes committed WAL.
                snapshot=Path(backup).absolute() if backup else source
                with sql(snapshot) as snap:
                    _,snaprows=validate(snapshot,snap)
                    if snaprows!=original:refuse()  # Never trust existence alone.
                    private_new(target,b"")
                    dest = sql(target, "rw", allow_empty=True)
                    try:snap.backup(dest)
                    finally:dest.close()
                dest=sql(target,"rw")
                try:
                    dest.execute("PRAGMA synchronous=FULL")
                    dest.execute("BEGIN IMMEDIATE")
                    if version==0 and backup is None:
                        dest.execute("ALTER TABLE device_nonces RENAME TO old_nonces")
                        for statement in SCHEMA.values():dest.execute(statement)
                        dest.execute("INSERT INTO nonce_metadata VALUES (1,2,?,0)",(secrets.token_hex(16),))
                        dest.execute("INSERT INTO device_nonces SELECT device_id,nonce,signed_at,accepted_at FROM old_nonces")
                        dest.execute("DROP TABLE old_nonces");dest.execute("PRAGMA user_version=2")
                    elif version!=2:refuse()
                    if history(dest)!=original:refuse()
                    identity=dest.execute("SELECT ledger_id FROM nonce_metadata").fetchone()[0]
                    dest.commit()
                    dest.execute("PRAGMA journal_mode=WAL")
                finally:dest.close()
                fd=os.open(target,os.O_RDONLY)
                try:os.fsync(fd)
                finally:os.close(fd)
                private_new(target.with_name(target.name+".initialized"),(json.dumps({"format":2,"ledger_id":identity},sort_keys=True)+"\n").encode())
                _fsync_directory(generation)
                target.with_name(target.name+".initializing").unlink();_fsync_directory(generation)
                self.binding(target,create=True);_fsync_directory(generation)
                NonceStore(target)
                return self.save(self.state(),"VERIFIED")

    def switch(self):
        with self.admin(),self.lock():
            s=self.state()
            if s["phase"]!="VERIFIED":refuse()
            target=Path(s["candidate"])
            self.binding(target)
            with sql(Path(s["active"]),"rw") as src:
                src.execute("BEGIN IMMEDIATE");_,original=validate(Path(s["active"]),src)
                with sql(target) as dst:_,copied=validate(target,dst)
                NonceStore(target)
                if original!=copied or fingerprint(original)!=s["checkpoint"]:refuse()
                return self.save(s,"SWITCHED",previous=s["active"],active=str(target))

    def resume(self):
        with self.admin(),self.lock():
            s=self.state()
            if s["phase"] not in {"SWITCHED","FROZEN"} or s.get("checkpoint") is None:refuse()
            target=Path(s["active"]);NonceStore(target)
            with sql(target) as db:
                _,rows=validate(target,db)
                if fingerprint(rows)!=s["checkpoint"]:refuse()
            return self.save(s,"ACTIVE")

    def recover(self):
        """Crash recovery only returns to frozen; never automatically serves."""
        with self.admin(),self.lock():
            s=self.state()
            if s["phase"] not in {"COPYING","VERIFIED","SWITCHED"}:refuse()
            with sql(Path(s["active"]),"rw") as src:
                src.execute("BEGIN IMMEDIATE");_,rows=validate(Path(s["active"]),src)
                if fingerprint(rows)!=s["checkpoint"]:refuse()
                return self.save(s,"FROZEN",candidate=None)
