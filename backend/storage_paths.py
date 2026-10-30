"""Reject aliases between independent stores before opening any SQLite file."""
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def same(first,second):
    a,b=Path(first),Path(second)
    return a.resolve()==b.resolve() or (a.exists() and b.exists() and os.path.samefile(a,b))

def validate_storage_paths(*, readings=None, auth=None):
    readings=Path(readings or os.environ.get('CARELINK_DATABASE_PATH',ROOT/'backend/carelink.db'))
    auth=Path(auth or os.environ.get('CARELINK_AUTH_DATABASE_PATH',ROOT/'.secrets/web-auth.sqlite3'))
    ledgers=[Path(os.environ.get('CARELINK_DEVICE_NONCE_DB',ROOT/'.secrets/device-nonces.sqlite3'))]
    root=os.environ.get('CARELINK_LEDGER_CONTROL_ROOT')
    if root:
        from .ledger_control import Controller,read_json
        try:
            if not Path(root).is_absolute():raise RuntimeError('Explicit absolute control root required')
            state=Controller(root).state()
            ledgers.append(Path(read_json(Path(state['inventory']))['source']))
            ledgers.extend(Path(state[k]) for k in ('active','candidate','previous') if state.get(k))
        except Exception:
            raise RuntimeError('Storage configuration unavailable') from None
        for path in (readings,auth):
            if Path(root).resolve() in (path.resolve(),*path.resolve().parents):
                raise RuntimeError('Independent stores must not overlap ledger control artifacts')
    if same(readings,auth):raise RuntimeError('Auth, readings and nonce stores must be distinct')
    for ledger in ledgers:
        artifacts=[ledger.with_name(ledger.name+s) for s in ('','-wal','-shm','-journal','.initialized','.initializing','.control')]
        if any(same(store,artifact) for store in (readings,auth) for artifact in artifacts):
            raise RuntimeError('Auth, readings and nonce stores must be distinct')
