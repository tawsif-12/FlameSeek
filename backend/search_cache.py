"""Small thread-safe process-local caches, invalidated by snapshot file identity."""
from collections import OrderedDict
import hashlib
import json
from threading import RLock
from time import monotonic


def snapshot_id(path):
    stat=path.stat()
    return (str(path.resolve()),stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)


def query_hash(payload):
    return hashlib.sha256(json.dumps(payload.model_dump(),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


class BoundedCache:
    def __init__(self,size=256,ttl=120):
        self.size=size;self.ttl=ttl;self.items=OrderedDict();self.lock=RLock()

    def get(self,key):
        with self.lock:
            value=self.items.get(key)
            if value is None:return None
            expires,result=value
            if expires<monotonic():
                del self.items[key];return None
            self.items.move_to_end(key)
            return result

    def put(self,key,result):
        with self.lock:
            self.items[key]=(monotonic()+self.ttl,result);self.items.move_to_end(key)
            while len(self.items)>self.size:self.items.popitem(last=False)


COUNTS=BoundedCache()
