__all__ = ['Pollable', 'PollableEvent']
# TODO look into eventfd
class BasePollable(object):
    """A pollable object.

    No locks so might not be threadsafe.  Best to call methods
    while some lock is acquired.
    """
    def __init__(self, r, w):
        self.r = r
        self.w = w
        self.on = False

    def __bool__(self):
        return self.on

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
        if not self.on:
            self.on = True
            self.w.write(b'0')
            self.w.flush()

    def clear(self):
        """Pop a byte, may hang if no bytes pushed."""
        if self.on:
            self.r.read(1)
            self.on = False

    def __del__(self):
        self.close()


import platform
if platform.system() == 'Windows':
    import socket
    from . import sockets
    class Pollable(BasePollable):
        def __init__(self):
            l = sockets.bind(('127.0.0.1', 0))
            try:
                l.listen(1)
                w = sockets.Sockfile(sockets.connect(('127.0.0.1', l.getsockname()[1])), 'wb')
                r, a = l.accept()
                r = sockets.Sockfile(r, 'rb')
            finally:
                l.close()
            super(Pollable, self).__init__(r, w)

else:
    import os
    class Pollable(BasePollable):
        def __init__(self):
            r, w = os.pipe()
            r = os.fdopen(r, 'rb')
            w = os.fdopen(w, 'wb')
            super(Pollable, self).__init__(r, w)


class PollableEvent(Pollable):
    """Takes a lock for use internally."""
    def __init__(self, lock):
        super(PollableEvent, self).__init__()
        self.lock = lock

    def __bool__(self):
        """Threadsafe. If lock is already grabbed, just check self.on."""
        with self.lock:
            return self.on

    def close(self):
        with self.lock:
            super(PollableEvent, self).close()

    def set(self):
        with self.lock:
            super(PollableEvent, self).set()

    def clear(self):
        with self.lock:
            super(PollableEvent, self).clear()
