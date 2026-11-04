"""Exclusive read-only leases; connections are never used by two requests at once."""
import atexit
from collections import OrderedDict
import os
import sqlite3
from threading import RLock, BoundedSemaphore
from time import monotonic

from search_cache import snapshot_id


class Lease:
    def __init__(self,pool,connection,identity):
        self.pool=pool;self.connection=connection;self.identity=identity

    def __getattr__(self,name):
        if self.connection is None:raise sqlite3.ProgrammingError('Snapshot lease is closed')
        return getattr(self.connection,name)

    def close(self):
        if self.connection is not None:
            con=self.connection;self.connection=None
            self.pool.release(con,self.identity)


class SnapshotPool:
    def __init__(self,size=8,idle_seconds=30,reuse=None):
        self.size=size;self.idle_seconds=idle_seconds
        self.reuse=(os.name!='nt' or os.getenv('FLAMESEEK_REUSE_SNAPSHOTS')=='1') if reuse is None else reuse
        self.idle=OrderedDict();self.lock=RLock();self.slots=BoundedSemaphore(size)

    def acquire(self,path):
        self.slots.acquire()
        try:
            identity=snapshot_id(path)
            with self.lock:
                now=monotonic()
                for key,(expires,con) in list(self.idle.items()):
                    if expires<now or (key[0]==identity[0] and key!=identity):
                        self.idle.pop(key);con.close()
                cached=self.idle.pop(identity,None)
            if cached:return Lease(self,cached[1],identity)
            # immutable=1 is opt-in: deployments must guarantee no in-place writes.
            immutable=os.getenv('FLAMESEEK_IMMUTABLE_SNAPSHOTS')=='1' and not any(
                path.with_name(path.name+suffix).exists() for suffix in ['-wal','-journal'])
            uri=path.resolve().as_uri()+'?mode=ro'+('&immutable=1' if immutable else '')
            con=sqlite3.connect(uri,uri=True,check_same_thread=False)
            con.row_factory=sqlite3.Row
            con.execute('PRAGMA query_only=ON')
            con.execute('PRAGMA mmap_size=268435456')
            con.execute('PRAGMA cache_size=-8192')
            after=snapshot_id(path)
            if identity!=after:
                con.close()
                raise sqlite3.OperationalError('Snapshot replaced while opening; retry request')
            return Lease(self,con,identity)
        except BaseException:
            self.slots.release();raise

    def release(self,con,identity):
        try:
            if not self.reuse:
                con.close();return
            con.create_function('area_contains',2,None)
            with self.lock:
                previous=self.idle.pop(identity,None)
                if previous:previous[1].close()
                self.idle[identity]=(monotonic()+self.idle_seconds,con)
                while len(self.idle)>self.size:
                    _,(_,old)=self.idle.popitem(last=False);old.close()
        finally:self.slots.release()

    def clear(self):
        with self.lock:
            for _,con in self.idle.values():con.close()
            self.idle.clear()


POOL=SnapshotPool()
atexit.register(POOL.clear)
