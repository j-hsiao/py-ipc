"""Register items into a poller."""
import socket
import uuid

from .. import sockfile
from ..formats import bases

class RWPair(object):
    """Read/Write pollable/selectable fd pair.

    Use sockets if windows, else os.pipe()
    """
    def __init__(self, sock=None):
        """Initialize.

        sock: a listening socket if provided.
            The sock will be connected to to create an in/out socket pair
            comopatible with select.select that can be used to interrupt
            any polling.
        """
        if sock is None:
            try:
                L = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            except AttributeError:
                L = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    L.bind(('127.0.0.1', 0))
                    L.listen(1)
                    self.r, self.w = self._from_listener(L)
                finally:
                    L.close()
            else:
                try:
                    L.bind('\0' + uuid.uuid4().hex)
                    L.listen(1)
                    self.r, self.w = self._from_listener(L)
                finally:
                    L.close()
        else:
            self.r, self.w = self._from_listener(sock)
        self.fileno = self.r.fileno

    def _from_listener(self, L):
        c = socket.socket(L.family, L.type)
        c.settimeout(0)
        try:
            c.connect(L.getsockname())
        except Exception:
            c.close()
            raise
        else:
            s, a = L.accept()
            s.settimeout(0)
            return (sockfile.Sockfile(s), sockfile.Sockfile(c))

    def clear(self):
        """Consume a byte."""
        try:
            self.r.read(1)
        except EnvironmentError as e:
            if e.errno not in bases.WOULDBLOCK:
                raise

    def set(self):
        """Send a byte to make polling return readable."""
        try:
            self.w.send(b'1')
        except EnvironmentError as e:
            if e.errno not in bases.WOULDBLOCK:
                raise

    def fileno(self):
        return self.fileno()

    def close(self):
        self.inp.close()
        self.out.close()


class NullLock(object):
    def __enter__(self):
        pass
    def __exit__(self, tp, exc, tb):
        pass

class PollRegister(RWPair):
    """Use fds to interrupt polling to add more items to be polled.

    Generally, register() will be called in a separate thread from the
    polling thread.  readinto1() will be called in the poller's poll()
    method.

    NOTE: if registering items for write polling, it would probably be
    more performant to somehow put the item into the w argument
    to WPoller or RWPoller instead of registering it.  This way, instead
    of polling first, it would try to write the data and only poll if
    it would have blocked.
    """

    def __init__(self, poller, sock=None, lock=NullLock()):
        super(PollRegister, self).__init__(sock)
        self.lock = lock
        self.poller = poller
        self.q = []

    def register(self, *args):
        """Add an item to be registered to the poll."""
        with self.lock:
            self.q.append(args)
            self.set()

    def readinto1(self, out):
        """Register items."""
        with self.lock:
            q = self.q
            self.q = []
        for args in q:
            self.clear()
            poller.register(*args)
        return -2
