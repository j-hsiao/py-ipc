# The bits returned in revents can include any of those specified in
# events, or one of the values POLLERR, POLLHUP, or POLLNVAL.  (These
# three bits are meaningless in the events field, and will be set in the
# revents field whenever the corresponding condition is true.)
#
# observations:
# poll performance is proportional to the number of events.  If data is
# large or constant, then fds will be constantly polled.  EPOLLET
# reduces number of polled events assuming that sockets are ready until
# EAGAIN/EWOULDBLOCK.
#
# 1. when event is fired all events are fired
#    ie: data to read, write blocked
#           poll->EPOLLIN
#           poll->nothing
#        remote reads
#           poll->EPOLLIN|EPOLLOUT
# 2. modify results in all events being fired again.
#
# ex. if get read->modify to remove read from mask
# but then ET doesn't really do anything...
# track whether reading or writing individually and ignore redundant?
#
# TODO considerations:
# 1. suppose polling gives HUP/ERR/NVAL, want to unregister it from
# poller (otherwise it'll keep getting polled)
# BUT. if it was already being processed in r/w?
# if w: would write->error?
# if r: would read->error?
# maybe no extra processing needed
# would unregister but already checked if need to unregister from poller
# so safe
#
# thought: handling hup/err/nval separately might not be necessary
# since trying to read/write if it was in error state should result
# in error and removing it/adding to bad anyways.
#
# for writer, get item into w somehow
# and also register somehow?
#
# but if register via read signal, can it be guaranteed to be
# registered before the write is handled?: add to w and register via the
# read signal, means w is never unregistered
__all__ = ['EpollPoller']
import select

from . import polling
from jhsiao.ipc import errnos

class EpollPoller(polling.Poller):
    r = select.EPOLLIN | select.EPOLLET
    w = select.EPOLLOUT | select.EPOLLET
    rw = r | w
    s = select.EPOLLIN
    def __init__(self):
        super(EpollPoller, self).__init__()
        self._items = {}
        self._poller = select.epoll()
        self[self] = self.s

    def __iter__(self):
        return iter(
            [item for item, readable, writable in self._items.values()])

    def __delitem__(self, item):
        fd = item.fileno()
        if self._items.pop(fd, None) is not None:
            self._poller.unregister(fd)

    def __setitem__(self, item, mode):
        fd = item.fileno()
        self._poller.register(fd, mode)
        self._items[fd] = [item, False, bool(select.EPOLLOUT & mode)]

    def close(self):
        super(EpollPoller, self).close()
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
            else:
                self[item] = mode
        for obj, data in flush:
            if self._items[obj.fileno()][2]:
                if not obj:
                    self._writing.append(obj)
            obj.write(data)

    def step(self, timeout=0):
        # TODO: poll just changes file state (if applicable)
        items = self._items
        reading = self._reading
        writing = self._writing
        cond = self._cond
        if timeout is None and (reading or writing):
            timeout = 0
        result = self._poller.poll(timeout)
        R = select.EPOLLIN
        W = select.EPOLLOUT
        for fd, md in result:
            L = items[fd]
            if md & R and not L[1]:
                L[1] = True
                reading.append(L[0])
            if md & W and not L[2]:
                L[2] = True
                if L[0]:
                    writing.append(L[0])
        with cond:
            wake = False
            if reading:
                sync = False
                data = self._data
                i = 0
                for item in reading:
                    try:
                        result = item.readinto1(data)
                    except EnvironmentError as e:
                        if e.errno in errnos.WOULDBLOCK:
                            items[item.fileno()][1] = False
                        elif e.errno == errnos.EINTR:
                            reading[i] = item
                            i += 1
                        else:
                            if item.fileno() in items:
                                raise
                    except Exception:
                        if item.fileno() in items:
                            raise
                    else:
                        if result is None or result == -2:
                            items[item.fileno()][1] = False
                        elif result == -1:
                            self._bad.append(item)
                            L = self._items.pop(item.fileno(), None)
                            if L is not None:
                                self._poller.unregister(item.fileno())
                                sync = sync or (item and L[2])
                            wake = True
                        else:
                            reading[i] = item
                            i += 1
                            wake = wake or result > 0
                del reading[i:]
                if sync:
                    writing = self._writing = [item for item in writing
                        if item.fileno() in self._items]
            if writing:
                i = 0
                sync = False
                for item in writing:
                    try:
                        result = item.flush1()
                    except EnvironmentError as e:
                        if e.errno in errnos.WOULDBLOCK:
                            items[item.fileno()][2] = False
                        elif e.errno == errnos.EINTR:
                            writing[i] = item
                            i += 1
                        else:
                            raise
                    else:
                        if result is None:
                            items[item.fileno()][2] = False
                        elif result == -1:
                            self._bad.append(item)
                            L = self._items.pop(item.fileno(), None)
                            if L is not None:
                                self._poller.unregister(item.fileno())
                                sync = sync or L[1]
                            wake = True
                        elif item:
                            writing[i] = item
                            i += 1
                del writing[i:]
                if sync:
                    self._reading = [item for item in reading
                        if item.fileno() in self._items]
            if wake:
                cond.notify()
            return self._running
