# The bits returned in revents can include any of those specified in
# events, or one of the values POLLERR, POLLHUP, or POLLNVAL.  (These
# three bits are meaningless in the events field, and will be set in the
# revents field whenever the corresponding condition is true.)
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
__all__ = ['RPoller', 'WPoller', 'RWPoller']
import select

from . import polling

class PPoller(object):
    r = select.POLLIN
    w = select.POLLOUT
    rw = r | w
    s = r
    bad = select.POLLHUP | select.POLLERR | select.POLLNVAL
    def __init__(self):
        self.items = {}
        self.poller = self.cls()
        self.poll = self.poller.poll

    def __iter__(self):
        return iter(self.items.values())

    def __delitem__(self, item):
        fd = item.fileno()
        if self.items.pop(fd, None) is not None:
            self.poller.unregister(fd)

    def __setitem__(self, item, mode):
        fd = item.fileno()
        self.poller.register(fd, mode)
        self.items[fd] = item

    def poll(self, timeout=-1):
        return self.poller.poll(timeout)

    def close(self):
        close = getattr(self.poller, 'close')
        if close is not None:
            close()


class RPPoller(PPoller, polling.RPoller):
    def __setitem__(self, item, mode):
        self.poller.register(item.fileno(), self.r)
        self.items[item.fileno()] = item

    def fill(self, result, r, out, bad):
        i = 0
        for item in r:
            result = item.readinto1(out)
            if result is None:
                self.poller.modify(item.fileno(), self.r)
            elif result == -1:
                bad.append(item)
                del self[item]
            else:
                r[i] = item
                i += 1
        del r[i:]
        for fd, m in result:
            item = self.items[fd]
            result = item.readinto1(out)
            if result == -1:
                bad.append(item)
                del self[item]
            elif result is not None and result != -2:
                r.append(item)
                self.poller.modify(fd, 0)

class WPPoller(PPoller, polling.WPoller):
    def fill(self, result, w, bad):
        i = 0
        for item in w:
            result = item.flush1()
            if result is None:
                fd = item.fileno()
                self.poller.modify(fd, self.w)
            elif result < 0:
                bad.append(item)
                del self[item]
            else:
                if item:
                    w[i] = item
                    i += 1
        del w[i:]
        for fd, m in result:
            if m & self.w:
                item = self.items[fd]
                result = item.flush1()
                if result is not None:
                    if result < 0:
                        bad.append(item)
                        del self[item]
                    else:
                        self.poller.modify(fd, 0)
                        if item:
                            w.append(item)
            else:
                self.items[fd].readinto1(None)

class RWPPoller(PPoller, polling.RWPoller):
    def __iter__(self):
        for item, mode in self.items.values():
            yield item

    def __setitem__(self, item, mode):
        fd = item.fileno()
        self.poller.register(fd, mode)
        self.items[fd] = [item, mode]

    def fill(self, result, r, w, out, bad):
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
                    self.poller.register(fd, self.r)
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
            if m & self.r:
                result = item.readinto1(out)
                if result == -1:
                    bad.append(item)
                    del self.items[fd]
                    self.poller.unregister(fd)
                elif result is not None and result != -2:
                    r.append(item)
                    if mode & self.w:
                        self.poller.modify(fd, self.w)
                        mode = pair[1] = self.w
                    else:
                        self.poller.modify(fd, 0)
                        mode = pair[1] = 0
            if m & self.w:
                result = item.flush1()
                if result is not None:
                    if result < 0:
                        bad.append(item)
                        del self.items[fd]
                        self.poller.unregister(fd)
                    else:
                        if mode & self.r:
                            self.poller.modify(fd, self.r)
                            pair[1] = self.r
                        else:
                            self.poller.modify(fd, 0)
                            pair[1] = 0
                        if item:
                            w.append(item)
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
    class DevpollPoller(object):

    class RDevpollPoller(RPPoller):
        pass

    class WDevpollPoller(WPPoller):
        pass

    class RWDevpollPoller(RWPPoller):
        pass

    RPoller = RDevpollPoller
    WPoller = WDevpollPoller
    RWPoller = RWDevpollPoller

if hasattr(select, 'poll'):

    class RPollPoller(PollPoller, RPPoller):
        pass

    class WPollPoller(PollPoller, WPPoller):
        pass

    class RWPollPoller(PollPoller, RWPPoller):
        pass

    RPoller = RPollPoller
    WPoller = WPollPoller
    RWPoller = RWPollPoller
