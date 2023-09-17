# The bits returned in revents can include any of those specified in
# events, or one of the values POLLERR, POLLHUP, or POLLNVAL.  (These
# three bits are meaningless in the events field, and will be set in the
# revents field whenever the corresponding condition is true.)
#
# Considerations:
# registering fds
#   1. polling handled in a separate thread
#   2. items are registered via a read signal
#         (writing to some fd to interrupt poll)
#   3. For read:
#         register once, and continue polling
#   4. For write:
#         If initial write is in main thread:
#             race condition: maybe something is being written then?
#         The register fd can try writing and only then add to w if not
#             fully written.  No race conditions.
# handling HUP/ERR/NVAL
#   1. suppose polling gives HUP/ERR/NVAL, want to unregister it from
#   poller (otherwise it'll keep getting polled)
#   BUT. if currently in r or w, would error, can just fully unregister
#   without removing from r or w
#   2. yet also, maybe don't need explicit handling? read/write would
#       indicate an error anyways...
#
# bad, closing:
#   if closed, fileno() may error, but unregister calls fileno()?
#   how to handle
#
# same thing may be added to bad multiple times...
# maybe use a set? or doesn't matter?
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

    def poll(self, timeout=None):
        if timeout is None:
            return self.poller.poll()
        else:
            return self.poller.poll(timeout*1000)

    def close(self):
        close = getattr(self.poller, 'close')
        if close is not None:
            close()


class RPPoller(PPoller, polling.RPoller):
    def __setitem__(self, item, mode):
        fd = item.fileno()
        self.poller.register(fd, self.r)
        self.items[fd] = item

    def fill(self, result, r, out, bad):
        i = 0
        for item in r:
            result = item.readinto1(out)
            if result is None:
                self.poller.modify(item.fileno(), self.r)
            elif result == -1:
                bad.add(item)
                del self[item]
            else:
                r[i] = item
                i += 1
        del r[i:]
        for fd, m in result:
            item = self.items[fd]
            result = item.readinto1(out)
            if result == -1:
                bad.add(item)
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
                bad.add(item)
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
                        bad.add(item)
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
                bad.add(item)
                del self[item]
            else:
                r[i] = item
                i += 1
        del r[i:]
        for fd, m in result:
            pair = self.items[fd]
            if m & self.bad:
                bad.add(pair[1])
                del self.items[fd]
                self.poller.unregister(fd)
                continue
            item, mode = pair
            md = None
            if m & self.r:
                result = item.readinto1(out)
                if result == -1:
                    bad.add(item)
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
                bad.add(item)
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
