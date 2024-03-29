"""Uniform polling interface.

Windows only supports select.
Note also that on windows, polling only works with sockets.
linux may have epoll etc, which generally have better performance.
"""
from __future__ import print_function
__all__ = ['Poller']
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
        implementation) or can be a str of flags 'rwxo' for general
        read/write/error/oneshot.
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

class OneshotWrapper(object):
    """Add one-shot-like behavior to raw poller."""
    def __init__(self, orig, oneshot_flag):
        """Iniitalize wrapper to add oneshot behavior."""
        self.orig = orig
        self.OFLAG = oneshot_flag
        self.RFLAG = ~oneshot_flag
        self.oneshot = set()
        self._unregister = orig.unregister
        self._register = orig.register
        self._modify = orig.modify
        self._poll = orig.poll
        self._close = orig.close

    def unregister(self, fd):
        self.oneshot.discard(fd)
        self._unregister(fd)
    def register(self, fd, flags):
        nflags = flags & self.RFLAG
        self._register(fd, nflags)
        if nflags != flags:
            self.oneshot.add(fd)
        else:
            self.oneshot.discard(fd)
    def modify(self, fd, flags):
        nflags = flags & self.RFLAG
        self._register(fd, nflags)
        if nflags != flags:
            self.oneshot.add(fd)
        else:
            self.oneshot.discard(fd)
    def poll(self, timeout=-1):
        ret = self._poll(timeout)
        for fd, ev in ret:
            if fd in self.oneshot:
                self._modify(fd, 0)
        return ret
    def close(self):
        self.oneshot.clear()
        self._close()

if hasattr(select, 'select'):
    class SelectPoller(object):
        """Wrap the select interface in poll-like interface."""
        backend = 'select'
        select = select.select
        RFLAGS = 1
        WFLAGS = 2
        XFLAGS = 4
        OFLAGS = 8
        NFLAGS = ((1, 'r'), (2, 'w'), (4, 'x'), (8, 'o'))
        def __init__(self):
            self.r = {}
            self.w = {}
            self.x = {}
            self.o = {}

        def __iter__(self):
            ret = dict(self.r)
            ret.update(self.w)
            ret.update(self.x)
            ret.update(self.o)
            return iter(ret.values())

        def unregister(self, item):
            fd = getfd(item)
            for d in (self.r, self.w, self.x, self.o):
                d.pop(fd, None)

        def _popornot(self, add, f, fd, item):
            if add:
                getattr(self, f)[fd] = item
            else:
                getattr(self, f).pop(fd, None)

        def register(self, item, flags):
            fd = getfd(item)
            if isinstance(flags, int):
                for v, f in self.NFLAGS:
                    self._popornot(flags & v, f, fd, item)
            else:
                for f in 'rwxo':
                    self._popornot(f in flags, f, fd, item)

        def _gpopornot(self, add, f, fd, item):
            if add:
                d = getattr(self, f)
                orig = d.get(fd, None)
                d[fd] = item
                return orig
            else:
                return getattr(self, f).pop(fd, None)

        def modify(self, item, flags):
            fd = getfd(item)
            orig = None
            if isinstance(flags, int):
                for v, f in self.NFLAGS:
                    orig = self._gpopornot(v&flags, f, fd, item) or orig
            else:
                for f in 'rwxo':
                    orig = self._gpopornot(f in flags, f, fd, item) or orig
            if orig is None:
                self.unregister(item)
                raise ValueError(
                    ('Tried to modify {} which '
                    'was never registered').format(item))

        def poll(self, timeout=None, events=False):
            """Note that if no active fds, then instant return with empty lists."""
            if timeout is not None and timeout < 0:
                timeout = None
            r = self.r
            w = self.w
            x = self.x
            try:
                lsts = self.select(r, w, x, timeout)
            except Exception:
                if not any((r,w,x)):
                    return ((),(),())
                else:
                    raise
            if events:
                ret = [
                    [(dct[fd], ev) for fd in lst]
                    for dct, lst, ev in zip(dct, lsts, (1,2,4))]
            else:
                ret = [
                    [dct[fd] for fd in lst]
                    for dct, lst in zip((r,w,x), lsts)]
            o = self.o
            if o:
                s = set(o)
                for dct, lst in zip((r,w,x), lsts):
                    for k in s.intersection(lst):
                        dct.pop(k, None)
            return ret

        def close(self):
            for f in 'rwxo':
                getattr(self, f).clear()
    Poller = SelectPoller

if hasattr(select, 'poll') or hasattr(select, 'devpoll'):
    class PPoller(_TruePoller):
        """Wrap the poll interface."""
        IN = select.POLLIN
        PRI = select.POLLPRI
        OUT = select.POLLOUT
        ERR = select.POLLERR
        RFLAGS = IN|PRI
        WFLAGS = OUT
        XFLAGS = ERR
        def OFLAGS():
            flags = [
                flag for flag in dir(select) if flag.startswith('POLL')]
            vals = [getattr(select, flag) for flag in flags]
            total = 0
            for val in vals:
                if isinstance(total, int):
                    total |= val
            shift = 0
            while 1:
                val = 1 << shift
                if not val & total:
                    return val
                shift += 1
        OFLAGS = OFLAGS()
        def __init__(self):
            super(PollPoller, self).__init__()
            self.e = OneshotWrapper(self.e, self.OFLAGS)
    if hasattr(select, 'devpoll'):
        class DevpollPoller(PPoller):
            cls = select.devpoll
            backend = 'devpoll'
        Poller = DevpollPoller
    if hasattr(select, 'poll'):
        class PollPoller(PPoller):
            cls = select.poll
            backend = 'poll'
        Poller = PollPoller

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
        OFLAGS = select.EPOLLONESHOT
    Poller = EpollPoller

try:
    id(Poller)
except NameError:
    raise Exception('could not find supported polling mechanisms')
