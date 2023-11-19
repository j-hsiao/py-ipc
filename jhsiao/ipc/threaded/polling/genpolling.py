"""Generic polling class, base for epoll, poll, devpoll.
"""
__all__ = ['GenPoller']
import select

from . import polling
from jhsiao.ipc import errnos

class AppendSet(set):
    append = set.add

class GenPoller(polling.Poller)
    TIMESCALE = 1
    # handlecontainer = AppendSet
    # TODO? should _reading/_writing be set instead of list?
    def __init__(self):
        super(GenPoller, self).__init__()
        # items: fd: [obj, readable?, writestate, curmode]
        # 0-2: 0=not writable
        # 1 = writable but nothing to write
        # 2 = currently writing
        self.items = {}
        self._poller = self.cls()
        self[self] = self.s
        self._rsync = False
        self._wsync = False

    def _poll(self, items, reading, writing, timeout):
        raise NotImplementedError
    def _new_item(self, item, mode):
        raise NotImplementedError
    def _update_mode(self, L, m):
        pass
    def __setitem__(self, item, mode):
        fd = item.fileno()
        current = self._items.get(fd)
        if current is None:
            self._items[fd] = self._new_item(item, mode)
            self._poller.register(fd, mode)
        else:
            if current[1] and not mode & self.ro:
                current[1] = False
                self._rsync = True
            if current[2] == 2 and not mode & self.wo:
                current[2] = 0
                self._wsync = True
            self._update_mode(current, mode)
            self._poller.modify(fd, mode)

    def __iter__(self):
        return iter([x[0] for x in self._items.values()])

    def __delitem__(self, item):
        fd = item.fileno()
        current = self._items.pop(fd, None)

    def _rm(self, item, r, w):
        fd = item.fileno()
        L = self._items.pop(fd, None)
        if L is None:
            return False
        if r:
            self._rsync = self._rsync or L[1]
        if w:
            self._wsync = self._wsync or L[2] == 2
        self._poller.unregister(fd)
        return True

    def close(self):
        super(GenPoller, self).close()
        self._poller.close()

    def readinto1(self, out):
        q = self._taskq
        self._taskq = []
        self._rwpair.readinto(bytearray(len(q)))
        for task, item, data in q:
            if task == self.WRITE:
                fd = item.fileno()
                L = self._items.get(fd)
                item.write(data)
                if L is not None and L[2] == 1:
                    L[2] = 2
                    self._writing.append(item)
            elif task == self.REGISTER:
                self[item] = mode
            elif task == self.UNREGISTER:
                self._rm(item, True, True)
        return -2

    def _reset_mode(self, fd, L, m):
        pass

    def _read(self, items, reading):
        data = self._data
        sync = self._rsync
        self._rsync = False
        wake = False
        i = 0
        for item in reading:
            if sync:
                try:
                    L = items.get(item.fileno())
                except Exception:
                    continue
                if L is None or not L[1]:
                    continue
            try:
                result = item.readinto1(data)
            except EnvironmentError as e:
                if e.errno in errnos.WOULDBLOCK:
                    result = None
                elif e.errno == errnos.EINTR:
                    result = 0
                else:
                    result = -1
            if result is None or result == -2:
                if result == -2 and self._rsync:
                    sync = True
                fd = item.fileno()
                L = items[fd]
                L[1] = False
                self._reset_mode(fd, L, self.r)
            elif result == -1:
                if self._rm(item, False, True)
                    self._bad.append(item)
                    wake = True
            else:
                reading[i] = item
                i += 1
                wake = wake or result > 0
        del reading[i:]
        return wake

    def _write(self, items, writing):
        sync = self._wsync
        wake = False
        i = 0
        for item in writing:
            if sync:
                try:
                    L = items.get(item.fileno())
                except Exception:
                    continue
                if L is None or not L[2]:
                    continue
            try:
                result = item.flush1()
            except EnvironmentError as e:
                if e.errno in errnos.WOULDBLOCK:
                    result = None
                elif e.errno == errnos.EINTR:
                    result = 0
                else:
                    result = -1
            if result is None:
                fd = item.fileno()
                L = items[fd]
                L[2] = 0
                self._reset_mode(fd, L, self.w)
            elif result == -1:
                if self._rm(item, True, False):
                    self._bad.append(item)
                    wake = True
            elif item:
                writing[i] = item
                i += 1
        del wake[i:]
        return wake

    def step(self, timeout=0):
        items = self._items
        reading = self._reading
        writing = self._writing
        cond = self._cond
        if timeout is None:
            timeout = 0 if reading or writing else -1
        else:
            timeout = timeout * self.TIMESCALE
        self._poll(items, reading, writing, timeout)
        with cond:
            wake = False
            if reading:
                wake = self._read(items, reading)
            if writing:
                wake = self._write(items, writing) or wake
            if wake:
                cond.notify()
            return self._running
