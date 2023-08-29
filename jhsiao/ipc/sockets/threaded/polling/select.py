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
    self.r = 1
    self.w = 2
    self.rw = 3


class RSelectPoller(SelectPoller, polling.RPoller):
    def __init__(self):
        self.r = set()
        self.unregister = self.r.discard

    def __iter__(self):
        return iter(self.r)

    def __setitem__(self, item, mode):
        self.r.add(item)

    def unregister(self, item):
        self.r.discard(item)

    def poll(self, timeout=None):
        return select.select(self.r, (), (), timeout)[0]

    def fill(self, result, r, out, bad):
        if result:
            self.r.difference_update(result)
            r.extend(result)
        i = 0
        for item in r:
            result = item.readinto1(out)
            if result is None or result == -2:
                self.r.add(item)
            elif result == -1:
                bad.append(item)
            else:
                r[i] = item
                i += 1
        del r[i:]

class _RW(SelectPoller):
    """Base class with r and w set attrs."""
    def __init__(self):
        super(_RW, self).__init__()
        self.r = set()
        self.w = set()

    def __iter__(self):
        return iter(self.r.union(self.w))

    def __delitem__(self, item):
        self.r.discard(item)
        self.w.discard(item)

    def __setitem__(self, item, mode):
        if mode == self.r:
            self.r.add(item)
            self.w.discard(item)
        elif mode == self.w:
            self.r.discard(item)
            self.w.add(item)
        elif mode == self.rw:
            self.r.add(item)
            self.w.add(item)
        else:
            raise ValueError('Bad mode: {}'.format(mode))

    def poll(self, timeout=None):
        return select.select(self.r, self.w, (), timeout)

class WSelectPoller(_RW, polling.WPoller):
    """Use select to poll for writes."""
    def fill(self, result, w, bad):
        r, extra, _ = result
        if r:
            for item in r:
                item.readinto1(None)
        if extra:
            self.w.difference_update(extra)
            w.extend(extra)
        i = 0
        for item in w:
            result = item.flush1()
            if result is None:
                self.w.add(item)
            elif result < 0:
                bad.append(item)
            else:
                if item:
                    w[i] = item
                    i += 1
        del w[i:]


class RWSelectPoller(_RW, polling.RWPoller):
    """Use select to poll for simultaneous read/write polling."""
    def fill(self, result, r, w, out, bad):
        er, ew, _ = result
        if er:
            r.extend(er)
            self.r.difference_update(er)
        if ew:
            w.extend(ew)
            self.w.difference_update(ew)
        i = 0
        for item in r:
            result = item.readinto1(out)
            if result is None or result == -2:
                self.r.add(item)
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
                self.w.add(item)
            elif result < 0:
                bad.append(item)
            else:
                if item:
                    w[i] = item
                    i += 1
        del w[i:]
