from __future__ import print_function
__all__ = [
    'RSelectPoller',
    'WSelectPoller',
    'RWSelectPoller',
]
import select
import sys

from . import polling

class SelectPoller(polling.Poller):
    r = 1
    w = 2
    rw = 3
    s = r

    def __init__(self, reimpl=False):
        super(SelectPoller, self).__init__()
        self._ritems = set()
        self._witems = set()
        self.reimpl = reimpl

    def __iter__(self):
        return iter(self.items)

    def __delitem__(self, item):
        self._ritems.discard(item)
        self._witems.discard(item)

    def __setitem__(self, item, mode):
        if mode & self.r:
            self._ritems.add(item)
        if mode & self.w:
            self._witems.add(item)

    def step(self):
        ritems = self._ritems
        witems = self._witems
        reading = self._reading
        writing = self._writing
        data = self._data
        bad = self._bad
        cond = self._cond
        r, w, x = select.select(ritems, witems, (), 0 if reading or writing else None)
        if w:
            witems.difference_update(w)
            writing.extend(w)
        if r:
            ritems.difference_update(r)
            reading.extend(r)
        with cond:
            wake = 0
            if reading:
                i = 0
                for item in reading:
                    result = item.readinto1(data)
                    if result is None or result == -2:
                        ritems.add(item)
                    elif result == -1:
                        bad.append(item)
                        wake = True
                    else:
                        reading[i] = item
                        i += 1
                        wake = wake or result > 0
            if writing:
                i = 0
                for item in writing:
                    result = item.flush1()
                    if result is None:
                        witems.add(item)
                    elif result == -1:
                        bad.append(item)
                        wake = True
                    else:
                        writing[i] = item
                        i += 1
            if wake:
                cond.notify()
            return self._running

    def _run(self):
        if not self.reimpl:
            return super(SelectPoller, self)._run()

        ritems = self._ritems
        witems = self._witems
        reading = self._reading
        writing = self._writing
        data = self._data
        bad = self._bad
        cond = self._cond
        try:
            while 1:
                r, w, x = select.select(ritems, witems, (), 0 if reading or writing else None)
                if w:
                    witems.difference_update(w)
                    writing.extend(w)
                if r:
                    ritems.difference_update(r)
                    reading.extend(r)
                with cond:
                    wake = 0
                    if reading:
                        i = 0
                        for item in reading:
                            result = item.readinto1(data)
                            if result is None or result == -2:
                                ritems.add(item)
                            elif result == -1:
                                bad.append(item)
                                wake = True
                            else:
                                reading[i] = item
                                i += 1
                                wake = wake or result > 0
                    if writing:
                        i = 0
                        for item in writing:
                            result = item.flush1()
                            if result is None:
                                witems.add(item)
                            elif result == -1:
                                bad.append(item)
                                wake = True
                            else:
                                writing[i] = item
                                i += 1
                    if wake:
                        cond.notify()
                    if not self._running:
                        return
        finally:
            with cond:
                self._running = False
                self._thread = None
