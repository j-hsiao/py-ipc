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
        self._items[fd] = [item, False, True]

    def close(self):
        super(EpollPoller, self).close()
        self.poller.close()

    def step(self, timeout=0):
        # TODO: poll just changes file state (if applicable)
        items = self._items
        reading = self._reading
        writing = self._writing
        cond = self._cond
        if timeout is None and (reading or writing):
            timeout = 0
        result = poller.poll(timeout)
        R = self.r
        W = self.w
        with cond:
            for fd, md in result:
                L = items[fd]
                if md & R and not L[1]:
                    reading.append(L[0])
                    L[1] = True
                if md & W and not L[2]:
                    writing.append(L[0])
                    L[2] = True
            wake = False
            if reading:
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
                            raise
                    else:
                        if result is None or result == -2:
                            items[item.fileno()][1] = False
                        elif result == -1:
                            self._bad.append(item)
                            wake = True
                        else:
                            reading[i] = item
                            i += 1
                            wake = wake or result > 0
            if writing:
                i = 0
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
                            wake = True
                        elif item:
                            writing[i] = item
                            i += 1


class RWPPoller(PPoller, polling.RWPoller):
    def __iter__(self):
        for item, mode in self.items.values():
            yield item

    def __setitem__(self, item, mode):
        fd = item.fileno()
        self.poller.register(fd, mode)
        self.items[fd] = [item, mode]

    def fill(self, result, r, w, out, bad):
        # impl details:
        # 1. handling w should come after polling so that handling of
        # interruption signal can be handled properly.  For instance,
        # adding an item for write handling will append to w and then
        # w is handled after.  Otherwise, the items would need to go
        # through another poll before writes are attempted.
        # (though maybe this isn't such a big deal?).  Write polled
        # objects if handled, may need to be appended to w.
        # But this may result in double-handling of the object.
        # (maybe this also doesn't matter that much since nonblocking
        # anyways...).  For now just go with "fair", 1 op per poll
        i = 0
        for item in r:
            result = item.readinto1(out)
            if result is None:
                fd = item.fileno()
                pair = self.items[fd]
                if pair[1]:
                    self.poller.modify(fd, self.rw)
                    pair[1] = self.rw
                else:
                    self.poller.modify(fd, self.r)
                    pair[1] = self.r
            elif result == -1:
                bad.append(item)
                del self[item]
            else:
                r[i] = item
                i += 1
        del r[i:]
        for fd, m in result:
            pair = self.items[fd]
            if m & self.bad:
                bad.append(pair[1])
                del self.items[fd]
                self.poller.unregister(fd)
                continue
            item, mode = pair
            md = None
            if m & self.r:
                result = item.readinto1(out)
                if result == -1:
                    bad.append(item)
                    del self.items[fd]
                    self.poller.unregister(fd)
                    continue
                elif result is not None and result != -2:
                    r.append(item)
                    if mode & self.w:
                        md = self.w
                    else:
                        md = 0
            if m & self.w:
                w.append(item)
                if mode & self.r:
                    md = self.r
                else:
                    md = 0
            if md is not None:
                self.poller.modify(fd, md)
                pair[1] = md
        i = 0
        for item in w:
            result = item.flush1()
            if result is None:
                fd = item.fileno()
                pair = self.items[fd]
                if pair[1]:
                    self.poller.modify(fd, self.rw)
                    pair[1] = self.rw
                else:
                    self.poller.register(fd, self.w)
                    pair[1] = self.w
            elif result < 0:
                bad.append(item)
                del self[item]
            elif item:
                w[i] = item
                i += 1
        del w[i:]



if hasattr(select, 'devpoll'):
    class RDevpollPoller(RPPoller):
        cls = select.devpoll

    class WDevpollPoller(WPPoller):
        cls = select.devpoll

    class RWDevpollPoller(RWPPoller):
        cls = select.devpoll

    RPoller = RDevpollPoller
    WPoller = WDevpollPoller
    RWPoller = RWDevpollPoller

if hasattr(select, 'poll'):
    class RPollPoller(RPPoller):
        cls = select.poll

    class WPollPoller(WPPoller):
        cls = select.poll

    class RWPollPoller(RWPPoller):
        cls = select.poll

    RPoller = RPollPoller
    WPoller = WPollPoller
    RWPoller = RWPollPoller
