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

class RSelectPoller(SelectPoller, polling.RPoller):
    def __init__(self):
        super(RSelectPoller, self).__init__()
        self.items = set()
        self.unregister = self.items.discard

    def __iter__(self):
        return iter(self.items)

    def __setitem__(self, item, mode):
        self.items.add(item)

    def unregister(self, item):
        self.items.discard(item)

    def poll(self, timeout=None):
        return select.select(self.items, (), (), timeout)[0]

    def fill(self, pollout, r, out, bad):
        if pollout:
            self.items.difference_update(pollout)
            r.extend(pollout)
        i = 0
        for item in r:
            result = item.readinto1(out)
            if result is None or result == -2:
                self.items.add(item)
            elif result == -1:
                bad.append(item)
            else:
                r[i] = item
                i += 1
        del r[i:]

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
