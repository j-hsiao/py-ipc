__all__ = ['RPoller', 'WPoller', 'RWPoller']
import select

from . import polling

polling.RPoller

class PPoller(object):
    r = select.POLLIN | select.POLLPRI
    w = select.POLLOUT
    rw = r | w
    s = r
    def __init__(self):
        self.items = {}
        self.poller = self.cls()
        self.poll = self.poller.poll

    def __iter__(self):
        return iter(self.items.values())

    def __delitem__(self, item):
        fd = item.fileno()
        if self.items.pop(fd, (0,0))[1]:
            self.poller.unregister(fd)

    def __setitem__(self, item, mode):
        fd = item.fileno()
        self.poller.register(fd, mode)
        self.items[fd] = item

    def poll(self, timeout=-1):
        return self.poller.poll(timeout)

    def close(self):
        self.poller.close()


class RPPoller(PPoller, polling.RPoller):
    def __setitem__(self, item, mode):
        self.poller.register(item.fileno(), self.r)
        self.items[item.fileno()] = item

    def fill(self, result, r, out, bad):
        i = 0
        for item in r:
            result = item.readinto1(out)
            if result is None:
                self.poller.register(item.fileno(), self.r)
            elif result == -1:
                bad.append(item)
                self.items.pop(item.fileno(), None)
            else:
                r[i] = item
                i += 1
        del r[i:]
        for fd, m in result:
            item = self.items[fd]
            result = item.readinto1(out)
            if result == -1:
                bad.append(item)
                self.poller.unregister(fd)
                self.items.pop(fd, None)
            elif result is not None and result != -2:
                r.append(item)
                self.poller.unregister(fd)


class WPPoller(PPoller, polling.WPoller):
    def fill(self, result, w, bad):
        i = 0
        for item in w:
            result = item.flush1()
            if result is None:
                self.poller.register(item.fileno(), self.w)
            elif result < 0:
                bad.append(item)
                self.items.pop(item.fileno(), None)
            else:
                if item:
                    w[i] = item
                    i += 1
                else:
                    self.items.pop(item.fileno(), None)
        del w[i:]
        for fd, m in result:
            if m & self.r:
                self.items[fd].readinto1(None)
            else:
                item = self.items[fd]
                result = item.flush1()
                if result is not None:
                    if result < 0:
                        bad.append(item)
                        self.poller.unregister(fd)
                        self.items.pop(fd, None)
                    else:
                        self.poller.unregister(fd)
                        if item:
                            w.append(item)
                        else:
                            self.items.pop(item.fileno(), None)

class RWPPoller(PPoller, polling.RWPoller):
    def __iter__(self):
        for item, mode in self.items.values():
            yield item

    def __setitem__(self, item, mode):
        # need to track read/write polling independently.
        fd = item.fileno()
        self.poller.register(fd, mode)
        self.items[fd] = [item, mode]

    def __delitem__(self, item):
        fd = item.fileno()
        if self.items.pop(fd, (0,0))[1]:
            self.poller.unregister(fd)

    def fill(self, result, r, w, out, bad):
        i = 0
        for item in r:
            result = item.readinto1(out)
            if result is None:
                fd = item.fileno()
                pair = self.items.get(fd, None)
                if pair is None:
                    pair = self.items[fd] = [item, 0]
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
        i = 0
        for item in w:
            result = item.flush1()
            if result is None:
                fd = item.fileno()
                pair = self.items.get(fd, None)
                if pair is None:
                    pair = self.items[fd] = [item, 0]
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
            else:
                fd = item.fileno()
                if not self.items.get(fd, (0,0))[1]:
                    del self.items[fd]
        del w[i:]
        # TODO handle newly polled objects
        for fd, m in result:
            item = self.items[fd]
            if m & self.r:
                result = item.readinto1(out)
                if result == -1:
                    bad.append(item)
                    self.poller.unregister(fd)
                    del self.items[fd]
                elif result is not None and result != -2:
                    r.append(item)
                    self.poller.unregister(fd)
            if m & self.w:
                result = item.flush1()
                if result is not None:
                    



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