"""One admission protocol for old/new HTTP entrypoints and business writes."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import inspect
import os

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from .ledger_control import Controller,ControlError

CURRENT=ContextVar("carelink_write_lease",default=None)


def controller():
    root=os.environ.get("CARELINK_LEDGER_CONTROL_ROOT")
    if not root or not os.path.isabs(root):raise ControlError("Explicit unified control root required")
    return Controller(root)


@contextmanager
def write_lease(selected_controller=None):
    lease=CURRENT.get()
    if lease and lease["valid"]:
        yield lease["path"];return
    with (selected_controller or controller()).admission() as path:
        lease={"path":path,"valid":True};token=CURRENT.set(lease)
        try:yield path
        finally:lease["valid"]=False;CURRENT.reset(token)


def guarded_write(function):
    @wraps(function)
    def wrapped(*args,**kwargs):
        try:
            with write_lease():return function(*args,**kwargs)
        except ControlError:raise HTTPException(503,"Device reception frozen or unavailable") from None
    # Preserve concrete annotations for FastAPI despite decorator globals.
    wrapped.__signature__=inspect.signature(function,eval_str=True)
    return wrapped


class UnifiedWriteGate:
    def __init__(self,app,controller=None):self.app,self.controller=app,controller

    async def __call__(self,scope,receive,send):
        path=scope.get("path","")
        protected=path.rstrip("/")=="/sensor-data" or path.startswith("/api/alerts")
        if scope["type"]!="http" or not protected:return await self.app(scope,receive,send)
        try:
            c=self.controller or controller();guard=c.admission()
            selected=await run_in_threadpool(guard.__enter__)
        except Exception:
            return await JSONResponse({"detail":"Device reception frozen or unavailable"},503)(scope,receive,send)
        lease={"path":selected,"valid":True};token=CURRENT.set(lease)
        scope["carelink_managed_ledger"]=str(selected)
        try:return await self.app(scope,receive,send)
        finally:
            lease["valid"]=False;CURRENT.reset(token);guard.__exit__(None,None,None)
