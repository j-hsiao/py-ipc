"""Generic polling class, base for epoll, poll, devpoll.
"""
__all__ = ['GenPoller']
import select

from . import polling

class GenPoller(polling.Poller)
    def __init__(self):
        super(GenPoller, self).__init__()
        self.items = {}
        self._poller = self.cls()
        self._sync = False
        self[self] = self.s

    def __iter__(self):
        return iter([x[0] for x in self._items.values()])

    def __delitem__(self, item):
        fd = item.fileno()
        if self._items.pop(fd, None) is not None:
            self._poller.unregister(fd)

    def __setitem__(self, item, mode):
        fd = item.fileno()
        current = self._items.get(fd)
        if current is None:
            self._items[fd] = [item, False, bool(mode & self.wo), mode]
        else:
            if not mode & self.ro and current[3] & self.ro and current[1]:
                self._sync = True
                current[1] = False
            if not mode & self.wo and current[3] & self.wo and current[2]:
                self._sync = True
                current[2] = False
            current[3] = mode
            self._poller.modify(fd, mode)
        if mode & self.wo and item:
            self._sync = True

    def close(self):
        super(GenPoller, self).close()
        self._poller.close()

    def readinto1(self, out):
        with self._cond:
            q = self._regq
            flush = self._flushq
            self._regq = []
            self._flushq = []
        self._rwpair.readinto(bytearray(len(q) + len(flush)))
        for item, mode in q:
            if mode is None:
                del self[item]
                self._sync = True
            else:
                self[item] = mode
        for obj, data in flush:
            if self._items[obj.fileno()][2]:
                if not obj:
                    self._writing.append(obj)
            obj.write(data)
        return -2

