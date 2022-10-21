class BasePollable(object):
    """A pollable object.

    The use case is to allow event-like interrupts while
    poll/select on sockets or stuff.
    This is implemented by making the returned fileno() readable or not
    by writing/reading a single byte per set/clear.
    There is no locking so might not be threadsafe.  It should
    generally be safe to call set from 1 thread and clear from another
    though.
    """
    def __init__(self):
        self.r = self.w = None

    def fileno(self):
        """Base class for polling."""
        return self.r.fileno()

    def close(self):
        if self.r is not None:
            self.r.close()
            self.r = None
        if self.w is not None:
            self.w.close()
            self.w = None

    def set(self):
        """Push a byte."""
        self.w.write(b'0')
        self.w.flush()

    def clear(self):
        """Pop a byte, may hang if no bytes pushed."""
        self.r.read(1)

    def __del__(self):
        self.close()


import platform
if platform.system() == 'Windows':
    import socket
    from . import sockets
    class Pollable(BasePollable):
        def __init__(self):
            super(Pollable, self).__init__()
            l = sockets.bind(('127.0.0.1', 0))
            try:
                l.listen(1)
                self.w = sockets.Sockfile(sockets.connect(('127.0.0.1', l.getsockname()[1])), 'wb')
                r, a = l.accept()
                self.r = sockets.Sockfile(r, 'rb')
            finally:
                l.close()

else:
    import os
    class Pollable(BasePollable):
        def __init__(self):
            super(Pollable, self).__init__()
            r, w = os.pipe()
            self.r = os.fdopen(r, 'rb')
            self.w = os.fdopen(w, 'wb')

if __name__ == '__main__':
    import select
    p = Pollable()
    print('should block')
    print(select.select((p,), (), (), 1))
    print('ok')
    p.set()
    print('immediate')
    print(select.select((p,), (), (), 1))
    print('ok')
    p.clear()
    print('should block')
    print(select.select((p,), (), (), 1))
    print('ok')
    p.close()
