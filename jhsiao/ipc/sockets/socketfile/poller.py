__all__ = ['Poller', 'SelectPoller']
import select

class _Poller(object):
    def __init__(self):
        pass

    def register(self, item, mode):
        """Register an item, must have fileno()."""
        pass

    def __call__(self, timeout=None):
        pass

    def unregister(self, fd):
        """Unregister an item."""
        pass

    def close(self):
        pass

class SelectPoller(_Poller):
    def __init__(self):
        self.r = {}
        self.w = {}
        self.x = {}

    def register(self, item, mode):
        """Register an item."""
        for md in mode:
            getattr(self, md)[item.fileno()] = item

    def unregister(self, fd):
        self.r.pop(fd, None)
        self.w.pop(fd, None)
        self.x.pop(fd, None)

    def __call__(self, timeout=None):
        return select.select(self.r, self.w, self.x)

    def close(self):
        self.r.clear()
        self.w.clear()
        self.x.clear()

Poller = SelectPoller

try:
    select.epoll
except AttributeError:
    pass
else:
    __all__.append('EPoller')
    class EPoller(_Poller):
        r = select.EPOLLIN | select.EPOLLPRI | select.EPOLLRDHUP | select.EPOLLRDNORM
        w = select.EPOLLOUT | select.EPOLLWRNORM
        x = select.EPOLLERR | select.EPOLLHUP

        def __init__(self):
            self.epoll = select.epoll()

        def __call__(self, timeout=None):
            r = []
            w = []
            x = []
            for fd, ev in self.epoll.poll(timeout):
                if ev & self.r:
                    r.append(fd)
                if ev & self.w:
                    w.append(fd)
                if ev & self.x:
                    x.append(fd)
            return r, w, x

        def close(self):
            self.epoll.close()

        def register(self, item, mode):
            flags = 0
            for flag in mode:
                flags |= getattr(self, flag)
            self.epoll.register(item, flags)

        def unregister(self, fd):
            self.epoll.unregister(fd)

    Poller = EPoller

if __name__ == '__main__':
    import socket
    l = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    l.bind(('127.0.0.1', 0))
    l.listen(1)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(l.getsockname())
    c, a = l.accept()


