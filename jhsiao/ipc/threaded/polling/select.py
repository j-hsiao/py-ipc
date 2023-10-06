from __future__ import print_function
__all__ = [
    'RSelectPoller',
    'WSelectPoller',
    'RWSelectPoller',
]
import select
import sys

from . import polling

class SelectPoller(object):
    r = 1
    w = 2
    rw = 3
    s = r

    def __init__(self):
        super(SelectPoller, self).__init__()

class RSelectPoller(SelectPoller, polling.RPoller):
    def __init__(self):
        super(RSelectPoller, self).__init__()
        self.items = set()
        self._changes = (set(), set())
        self._ready = []

    def readinto1(self, out):
        with self._cond:
            add, rm = self._changes
            items = self.items
            items.update(add)
            items.difference_update(rm)
            add.clear()
            rm.clear()

    def __iter__(self):
        return iter(self.items)

    def __delitem__(self, item):
        self.items.discard(item)
    def __setitem__(self, item, mode):
        self.items.add(item)

    def register(self, item, mode):
        with self._cond:
            toadd, torm = self._changes
            toadd.add(item)
            torm.discard(item)

    def unregister(self, item):
        with self._cond:
            toadd, torm = self._changes
            toadd.discard(item)
            torm.add(item)

    def step(self):
        ready = self._ready
        items = self.items
        r, w, x = select.select(items, (), (), 0 if self._ready else None)
        if r:
            items.difference_update(r)
            ready.extend(r)
        with self._cond:
            i = 0
            received = self.received
            for item in ready:
                result = item.readinto1(received)
                if result is None or result == -2:
                    items.add(item)
                elif result == -1:
                    self.bad.append(item)
                else:
                    ready[i] = item
                    i += 1
            ret = self._running:
        del ready[i:]
        return ret


class _RW(SelectPoller):
    """Base class with _r and _w set attrs."""
    def __init__(self):
        super(_RW, self).__init__()
        self._r = set()
        self._w = set()

    def __iter__(self):
        return iter(self._r.union(self._w))

    def __delitem__(self, item):
        self._r.discard(item)
        self._w.discard(item)

    def __setitem__(self, item, mode):
        if mode == self._r:
            self._r.add(item)
            self._w.discard(item)
        elif mode == self._w:
            self._r.discard(item)
            self._w.add(item)
        elif mode == self._rw:
            self._r.add(item)
            self._w.add(item)
        else:
            raise ValueError('Bad mode: {}'.format(mode))

    def poll(self, timeout=None):
        return select.select(self._r, self._w, (), timeout)

class WSelectPoller(_RW, polling.WPoller):
    """Use select to poll for writes."""
    def fill(self, pollout, w, bad):
        rpoll, wpoll, _ = pollout
        if rpoll:
            for item in rpoll:
                item.readinto1(None)
        if wpoll:
            self._w.difference_update(wpoll)
            w.extend(wpoll)
        i = 0
        for item in w:
            result = item.flush1()
            if result is None:
                self._w.add(item)
            elif result < 0:
                bad.append(item)
            else:
                if item:
                    w[i] = item
                    i += 1
        del w[i:]


class RWSelectPoller(_RW, polling.RWPoller):
    """Use select to poll for simultaneous read/write polling."""
    def fill(self, pollout, r, w, out, bad):
        rpoll, wpoll, _ = pollout
        if rpoll:
            r.extend(rpoll)
            self._r.difference_update(rpoll)
        if wpoll:
            w.extend(wpoll)
            self._w.difference_update(wpoll)
        i = 0
        for item in r:
            result = item.readinto1(out)
            if result is None or result == -2:
                self._r.add(item)
            elif result == -1:
                bad.append(item)
            else:
                r[i] = item
                i += 1
        del r[i:]
        i = 0
        for item in w:
            result = item.flush1()
            if result is None:
                self._w.add(item)
            elif result < 0:
                bad.append(item)
            else:
                if item:
                    w[i] = item
                    i += 1
        del w[i:]
