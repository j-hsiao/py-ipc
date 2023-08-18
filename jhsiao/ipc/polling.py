"""Uniform polling interface.

Windows only supports select.
Note also that on windows, polling only works with sockets.
linux may have epoll etc, which generally have better performance.
"""
from __future__ import print_function
__all__ = ['Poller']
from collections import defaultdict
import select
import sys
from itertools import chain
import traceback
if sys.version_info.major < 3:
    from itertools import imap as map

def getfd(item):
    """Get the fd if not an fd (int)."""
    if isinstance(item, int):
        return item
    else:
        return item.fileno()

class _Poller(object):
    """Base poller class.

    Registered items should have a fileno() or be a fileno.
    In addition to methods, subclasses should also have the following
    attributes used as mode for modify() and register():
        r: poll reading
        w: poll writing
        x: poll error
        o: use one-shot semantics
        flags: dict of each rwxo to int
    Registered items when polled are returned as was registered.
    """
    def __iter__(self):
        """Iterate on items that have been registered."""
        raise NotImplementedError

    def __delitem__(self, item):
        """Unregister an item, defaults to calling unregister()."""
        self.unregister(item)

    def __setitem__(self, item, mode):
        """Register an item.  Defaults to calling register()."""
        self.register(item, mode)

    def unregister(self, item):
        """Unregister an item by value or fd."""
        del self[item]

    def register(self, item, mode):
        """Register an item by value or fd.

        `item` will be what is returned if polled.
        `mode` should be a bitwise or of rwxo attributes.
            Alternatively, it can be a string containing any
            of 'rwxo' with the same corresponding meanings as the
            attributes.

        Items that are already registered will be unregistered first.
        """
        self[item] = mode

    def close(self):
        raise NotImplementedError

    def anypoll(self, timeout=-1, events=False):
        """Poll for events.

        Same as poll() but assume all registered items will only
        ever be triggered by a single particular type of event.
        All items will be returned in a single list.
        This might be a little more efficient for true pollers because
        they don't need to be added to corresponding lists.
        There should be at least 1 registered fd for polling.
        """
        raise NotImplementedError

    def poll(self, timeout=-1, events=False):
        """Poll for events.

        Negative timeout or None means no timeout.
        Returns 3 lists of results corresponding to read, write,  and
        error based on the polled event.  If events is set, then also
        return the corresponding event that was triggered.
        There should be at least 1 registered fd for polling.
        """
        raise NotImplementedError

    def _get_flags(self, mode):
        """Translate str flags into int flags."""
        if isinstance(mode, int):
            return mode
        flags = 0
        for m in mode:
            flags |= self.flags[m]
        return flags

if hasattr(select, 'select'):
    __all__.append('SelectPoller')
    class SelectPoller(_Poller):
        """Wrap the select interface in poll-like interface.

        NOTE: calling select with all empty lists results in invalid
        arguments on windows which will result in instant return of
        empty lists.
        """
        backend = 'select'
        select = select.select
        r = 1
        w = 2
        x = 4
        o = 8
        n = ~8
        flags = dict(r=r, w=w, x=x, o=o)
        NFLAGS = ((1, 'r'), (2, 'w'), (4, 'x'), (8, 'o'))

        def __init__(self):
            self.items = {}
            self.ritems = set()
            self.witems = set()
            self.xitems = set()
            self.ofds = set()
            self.strmap = dict(
                r=self.ritems, w=self.witems,
                x=self.xitems, o=self.ofds)
            self.flagmap = {
                self.r: self.ritems, self.w: self.witems,
                self.x: self.xitems, self.o: self.ofds}

        def __iter__(self):
            return iter(self.items.values())

        def __delitem__(self, item):
            fd = getfd(item)
            self.items.pop(fd)
            for st in self.strmap.values():
                st.discard(fd)

        def __setitem__(self, item, mode):
            fd = getfd(item)
            if isinstance(mode, int):
                for flag, d in self.flagmap.items():
                    if mode & flag:
                        d.add(fd)
                    else:
                        d.discard(fd)
            else:
                for flag, d in self.strmap.items():
                    if flag in mode:
                        d.add(fd)
                    else:
                        d.discard(fd)
            self.items[fd] = item

        def close(self):
            self.items.clear()
            for v in self.strmap.values():
                v.clear()

        def anypoll(self, timeout=-1, events=False):
            if timeout is not None and timeout < 0:
                timeout = None
            try:
                rwx = select.select(
                    self.ritems, self.witems, self.xitems, timeout)
            except OSError:
                if not self.ritems and not self.witems and not self.xitems:
                    return []
                raise
            if events:
                fdflags = defaultdict(int)
                for fds, flag in zip(rwx, (self.r, self.w, self.x)):
                    for fd in fds:
                        fdflags[fd] |= flag
                oneshots = self.ofds.intersection(fdflags)
                ret = [
                    (self.items[fd], flag)
                    for fd, flag in fdflags.items()]
            else:
                allfds = set().union(*rwx)
                oneshots = self.ofds.intersection(allfds)
                ret = [self.items[fd] for fd in allfds]
            if oneshots:
                self.ritems.difference_update(oneshots)
                self.witems.difference_update(oneshots)
                self.xitems.difference_update(oneshots)
            return ret

        def poll(self, timeout=None, events=False):
            """Note that if no active fds, then instant return with empty lists."""
            if timeout is not None and timeout < 0:
                timeout = None
            try:
                rwx = select.select(
                    self.ritems, self.witems, self.xitems, timeout)
            except OSError:
                if not self.ritems and not self.witems and not self.xitems:
                    return [], [], []
                raise
            allfds = set().union(*rwx)
            oneshots = self.ofds.intersection(allfds)
            if events:
                ret = [
                    [(self.items[fd], flag) for fd in fds]
                    for fds, flag in zip(rwx, (self.r, self.w, self.x))]
            else:
                ret = [[self.items[fd] for fd in fds] for fds in rwx]
            if oneshots:
                self.ritems.difference_update(oneshots)
                self.witems.difference_update(oneshots)
                self.xitems.difference_update(oneshots)
            return ret

    Poller = SelectPoller

if hasattr(select, 'poll') or hasattr(select, 'devpoll'):
    class _PPoller(_Poller):
        """_Poller to wrap devpoll or poll with oneshot behavior."""
        IN = select.POLLIN
        PRI = select.POLLPRI
        OUT = select.POLLOUT
        ERR = select.POLLERR
        r = IN|PRI
        w = OUT
        x = ERR
        o = 2 ** max([
            getattr(select, flag)
            for flag in dir(select)
            if flag.startswith('POLL')
        ]).bit_length()
        flags = dict(r=r, w=w, x=x, o=o)
        n = ~o

        def __init__(self):
            """Iniitalize wrapper to add oneshot behavior."""
            self.e = self.cls()
            self.items = {}
            self.oneshot = set()

        def __iter__(self):
            return iter(self.items.values())

        def __delitem__(self, item):
            fd = getfd(item)
            if self.items.pop(fd, None) is not None:
                self.oneshot.discard(fd)
                try:
                    self.e.unregister(fd)
                except Exception:
                    traceback.print_exc()

        def __setitem__(self, item, mode):
            fd = getfd(item)
            if fd in self.items:
                self.unregister(fd)
            mode = self._get_flags(mode)
            flags = mode & self.n
            self.e.register(fd, flags)
            self.items[fd] = item
            if flags != mode:
                self.oneshot.add(fd)
            else:
                self.oneshot.discard(fd)

        def anypoll(self, timeout=-1, events=False):
            if timeout is None:
                timeout = -1
            if timeout > 0:
                timeout *= 1000
            vals = self.e.poll(timeout)
            fds = [fd for fd, ev in vals]
            oneshots = self.oneshot.intersection(fds)
            if events:
                ret = [(self.items[fd], flag) for fd, flag in vals]
            else:
                ret = [self.items[fd] for fd in fds]
            for fd in oneshots:
                self.unregister(fd)
            return ret

        def poll(self, timeout=-1, events=False):
            if timeout is None:
                timeout = -1
            if timeout > 0:
                timeout *= 1000
            vals = self.e.poll(timeout)
            if events:
                ret = [
                    [(self.items[fd], flag) for fd, flag in vals if flag & mode]
                    for mode in (self.r, self.w, self.x)]
            else:
                ret = [
                    [self.items[fd] for fd, flag in vals if flag & mode]
                    for mode in (self.r, self.w, self.x)]
            oneshots = self.oneshot.intersection([fd for fd, ev in vals])
            for fd in oneshots:
                self.unregister(fd)
            return ret

        def close(self):
            self.e.close()
            self.items.clear()

    if hasattr(select, 'devpoll'):
        __all__.append('DevpollPoller')
        class DevpollPoller(_PPoller):
            cls = select.devpoll
            backend = 'devpoll'
        Poller = DevpollPoller
    if hasattr(select, 'poll'):
        __all__.append('PollPoller')
        class PollPoller(_PPoller):
            cls = select.poll
            backend = 'poll'
        Poller = PollPoller

if hasattr(select, 'epoll'):
    __all__.append('EpollPoller')
    class EpollPoller(_Poller):
        """Wrap an actual polling object.

        Subclasses should have the following attributes:
            cls: the actual implementing class
        """
        cls = select.epoll
        backend = 'epoll'
        IN = select.EPOLLIN
        OUT = select.EPOLLOUT
        PRI = select.EPOLLPRI
        ERR = select.EPOLLERR
        HUP = select.EPOLLHUP
        ET = select.EPOLLET
        ONESHOT = select.EPOLLONESHOT
        EXCLUSIVE = select.EPOLLEXCLUSIVE
        RDHUP = select.EPOLLRDHUP
        RDNORM = select.EPOLLRDNORM
        RDBAND = select.EPOLLRDBAND
        WRNORM = select.EPOLLWRNORM
        WRBAND = select.EPOLLWRBAND
        MSG = select.EPOLLMSG
        r = IN|RDNORM|RDBAND
        w = OUT|WRNORM|WRBAND
        x = ERR
        o = select.EPOLLONESHOT
        flags = dict(r=r, w=w, x=x, o=o)
        def __init__(self):
            self.e = self.cls()
            self.items = {}

        def __iter__(self):
            return iter(self.items.values())

        def __delitem__(self, item):
            fd = getfd(item)
            if self.items.pop(fd, None) is not None:
                try:
                    self.e.unregister(fd)
                except Exception:
                    traceback.print_exc()

        def __setitem__(self, item, mode):
            fd = getfd(item)
            if fd in self.items:
                self.unregister(fd)
            self.e.register(fd, self._get_flags(mode))
            self.items[fd] = item

        def anypoll(self, timeout=-1, events=False):
            if timeout is None:
                timeout = -1
            if events:
                return self.e.poll(timeout)
            else:
                return [self.items[fd] for fd, ev in self.e.poll(timeout)]

        def poll(self, timeout=-1, events=False):
            if timeout is None:
                timeout = -1
            vals = self.e.poll(timeout)
            if events:
                return [
                    [(self.items[fd], flag) for fd, flag in vals if flag & mode]
                    for mode in (self.r, self.w, self.x)]
            else:
                return [
                    [self.items[fd] for fd, flag in vals if flag & mode]
                    for mode in (self.r, self.w, self.x)]

        def close(self):
            self.e.close()
            self.items.clear()

    Poller = EpollPoller

try:
    id(Poller)
except NameError:
    raise Exception('could not find supported polling mechanisms')
