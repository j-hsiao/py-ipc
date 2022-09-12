"""Uniform polling interface.

Windows only supports select.
Note also that on windows, polling only works with sockets.
linux may have epoll etc, which generally have better performance.
"""
from __future__ import print_function
import select
import sys
from itertools import chain
import traceback
if sys.version_info.major < 3:
    from itertools import imap as map

def getfd(item):
    if hasattr(item, 'fileno'):
        return item.fileno()
    else:
        return item

class BasePoller(object):
    """Base poller class.  Set the interface.

    Registered items should have a fileno() or be a fileno.
    """
    def __iter__(self):
        """Iterate on items that have been registered."""
        raise NotImplementedError

    def unregister(self, item):
        """Unregister an item by value or fd."""
        raise NotImplementedError
    def register(self, item, mode):
        """Register an item by value or fd.

        item will be what is returned if polled.
        mode can be an int (varies by class based on the underlying
        implementation) or can be a str of flags 'rwx' for general
        read/write/error.
        """
        raise NotImplementedError
    def modify(self, item, mode):
        """Change registration mode of item.

        Can also be used to change the returned value when the
        corresponding fd is polled.
        eg:
            with open('filename', 'w') as f:
                poller.register(f, mode)
                # polling would return f the file object
                poller.modify(f.fileno(), mode)
                # now polling will return the fileno
        """
        raise NotImplementedError

    def close(self):
        raise NotImplementedError

    def poll(self, timeout=-1, events=False):
        """Poll for events.

        Negative timeout or None means no timeout.
        Returns 3 lists of results corresponding to read, write,  and
        error based on the polled event.  If events is set, then also
        return the corresponding event that was triggered.
        """
        raise NotImplementedError

class _TruePoller(BasePoller):
    """Wrap an actual polling object.

    Subclasses should have the following attributes:
        cls: the actual implementing class
        RFLAGS, WFLAGS, XFLAGS: a mask of corresponding  read, write,
            and error flags.
    """
    def __init__(self):
        self.e = self.cls()
        self.items = {}

    def __iter__(self):
        return iter(self.items.values())

    def unregister(self, item):
        fd = getfd(item)
        self.items.pop(fd)
        try:
            self.e.unregister(fd)
        except Exception:
            traceback.print_exc()

    def register(self, item, mode):
        fd = getfd(item)
        if fd in self.items:
            self.unregister(fd)
        self.e.register(fd, self._get_flags(mode))
        self.items[fd] = item

    def modify(self, item, mode):
        fd = getfd(item)
        if fd not in self.items:
            raise ValueError(
                'Tried to modify {} which was never registered'.format(item))
        self.e.modify(fd, self._get_flags(mode))
        self.items[fd] = item

    def poll(self, timeout=-1, events=False):
        if timeout is None:
            timeout = -1
        r, w, x = [], [], []
        for fd, ev in self.e.poll(timeout):
            item = (self.items[fd], ev) if events else self.items[fd]
            if ev & self.RFLAGS:
                r.append(item)
            if ev & self.WFLAGS:
                w.append(item)
            if ev & self.XFLAGS:
                x.append(item)
        return r, w, x
    def close(self):
        self.e.close()
        self.items.clear()

    def _get_flags(self, mode):
        """Translate str flags into int flags."""
        if isinstance(mode, int):
            return mode
        flags = 0
        for m in mode:
            flags |= getattr(self, m.upper()+'FLAGS', 0)
        return flags

if hasattr(select, 'epoll'):
    class EpollPoller(_TruePoller):
        """Wrap the epoll interface."""
        cls = select.epoll
        backend = 'epoll'
        cls = select.epoll
        IN = select.EPOLLIN
        PRI = select.EPOLLPRI
        RDNORM = select.EPOLLRDNORM
        RDBAND = select.EPOLLRDBAND
        OUT = select.EPOLLOUT
        WRNORM = select.EPOLLWRNORM
        WRBAND = select.EPOLLWRBAND
        ERR = select.EPOLLERR
        RFLAGS = IN|PRI|RDNORM|RDBAND
        WFLAGS = OUT|WRNORM|WRBAND
        XFLAGS = ERR
if hasattr(select, 'poll'):
    class PollPoller(_TruePoller):
        """Wrap the poll interface."""
        cls = select.poll
        backend = 'poll'
        IN = select.POLLIN
        PRI = select.POLLPRI
        OUT = select.POLLOUT
        ERR = select.POLLERR
        RFLAGS = IN|PRI
        WFLAGS = OUT
        XFLAGS = ERR
    if hasattr(select, 'devpoll'):
        class DevpollPoller(PollPoller):
            cls = select.devpoll
            backend = 'devpoll'

elif hasattr(select, 'devpoll'):
    class DevpollPoller(_TruePoller):
        """Wrap the devpoll interface."""
        cls = select.devpoll
        backend = 'devpoll'
        IN = select.POLLIN
        PRI = select.POLLPRI
        OUT = select.POLLOUT
        ERR = select.POLLERR
        RFLAGS = IN|PRI
        WFLAGS = OUT
        XFLAGS = ERR


if hasattr(select, 'select'):
    class SelectPoller(object):
        """Wrap the select interface."""
        backend = 'select'
        select = select.select
        def __init__(self, verbose=False):
            self.verbose = verbose
            self.r = {}
            self.w = {}
            self.x = {}

        def __iter__(self):
            ret = dict(self.r)
            ret.update(self.w)
            ret.update(self.x)
            return iter(ret.values())

        def poll(self, timeout=None, events=False):
            if timeout < 0:
                timeout = None
            dcts = (self.r, self.w, self.x)
            r, w, x = dcts
            lsts = self.select(r, w, x, timeout)
            if events:
                return [
                    [(dct[fd],0) for fd in lst]
                    for lst, dct in zip(lsts, dcts)]
            else:
                return [
                    list(map(dct.__getitem__, lst))
                    for lst, dct in zip(lsts, dcts)]

        def register(self, item, mode):
            self.unregister(item)
            fd = getfd(item)
            for m in mode:
                getattr(self, m)[fd] = item

        def modify(self, item, mode):
            fd = getfd(item)
            orig = self.r.pop(fd, None)
            orig = self.w.pop(fd, None) or orig
            orig = self.x.pop(fd, None) or orig
            if orig is None:
                raise ValueError(
                    ('Tried to modify {} which '
                    'was never registered').format(item))
            for m in mode:
                getattr(self, m)[fd] = item

        def unregister(self, item):
            fd = getfd(item)
            for d in (self.r, self.w, self.x):
                d.pop(fd, None)

        def close(self):
            pass

if hasattr(select, 'epoll'):
    Poller = EpollPoller
elif hasattr(select, 'poll'):
    Poller = PollPoller
elif hasattr(select, 'devpoll'):
    Poller = DevpollPoller
elif hasattr(select, 'select'):
    Poller = SelectPoller
else:
    raise Exception('could not find supported polling mechanisms')
