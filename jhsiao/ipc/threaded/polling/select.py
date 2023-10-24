from __future__ import print_function
__all__ = ['SelectPoller']
import select
import sys

from . import polling
from jhsiao.ipc import errnos

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
        self[self] = self.s

    def __iter__(self):
        return iter(self._ritems.union(self._witems))

    def __delitem__(self, item):
        self._ritems.discard(item)
        self._witems.discard(item)

    def __setitem__(self, item, mode):
        if mode & self.r:
            self._ritems.add(item)
        if mode & self.w:
            self._witems.add(item)

    def step(self, timeout=0):
        ritems = self._ritems
        witems = self._witems
        reading = self._reading
        writing = self._writing
        cond = self._cond
        if timeout is None and (reading or writing):
            timeout = 0
        r, w, x = select.select(ritems, witems, (), timeout)
        if w:
            witems.difference_update(w)
            writing.extend(w)
        if r:
            ritems.difference_update(r)
            reading.extend(r)
        with cond:
            wake = False
            if reading:
                data = self._data
                i = 0
                for item in reading:
                    try:
                        result = item.readinto1(data)
                    except EnvironmentError as e:
                        if e.errno in errnos.WOULDBLOCK:
                            ritems.add(item)
                        elif e.errno != errnos.EINTR:
                            raise
                        else:
                            reading[i] = item
                            i += 1
                    else:
                        if result is None or result == -2:
                            ritems.add(item)
                        elif result == -1:
                            self._bad.append(item)
                            wake = True
                        else:
                            reading[i] = item
                            i += 1
                            wake = wake or result > 0
                del reading[i:]
            if writing:
                i = 0
                for item in writing:
                    try:
                        result = item.flush1()
                    except EnvironmentError as e:
                        if e.errno in errnos.WOULDBLOCK:
                            witems.add(item)
                        elif e.errno != errnos.EINTR:
                            raise
                        else:
                            writing[i] = item
                            i += 1
                    else:
                        if result is None:
                            witems.add(item)
                        elif result == -1:
                            self._bad.append(item)
                            wake = True
                        elif item:
                            writing[i] = item
                            i += 1
                del writing[i:]
            if wake:
                cond.notify()
            return self._running

#    def _run(self):
#        if not self.reimpl:
#            return super(SelectPoller, self)._run()
#
#        ritems = self._ritems
#        witems = self._witems
#        reading = self._reading
#        writing = self._writing
#        cond = self._cond
#        try:
#            while 1:
#                r, w, x = select.select(ritems, witems, (), 0 if reading or writing else None)
#                if w:
#                    witems.difference_update(w)
#                    writing.extend(w)
#                if r:
#                    ritems.difference_update(r)
#                    reading.extend(r)
#                with cond:
#                    wake = 0
#                    if reading:
#                        data = self._data
#                        i = 0
#                        for item in reading:
#                            try:
#                                result = item.readinto1(data)
#                            except EnvironmentError as e:
#                                if e.errno not in errnos.WOULDBLOCK:
#                                    raise
#                                ritems.add(item)
#                            else:
#                                if result is None or result == -2:
#                                    ritems.add(item)
#                                elif result == -1:
#                                    self._bad.append(item)
#                                    wake = True
#                                else:
#                                    reading[i] = item
#                                    i += 1
#                                    wake = wake or result > 0
#                        del reading[i:]
#                    if writing:
#                        i = 0
#                        for item in writing:
#                            try:
#                                result = item.flush1()
#                            except EnvironmentError as e:
#                                if e.errno not in errnos.WOULDBLOCK:
#                                    raise
#                                witems.add(item)
#                            else:
#                                if result is None:
#                                    witems.add(item)
#                                elif result == -1:
#                                    self._bad.append(item)
#                                    wake = True
#                                else:
#                                    writing[i] = item
#                                    i += 1
#                        del writing[i:]
#                    if wake:
#                        cond.notify()
#                    if not self._running:
#                        return
#        finally:
#            with cond:
#                self._running = False
#                self._thread = None
