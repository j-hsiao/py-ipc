__all__ = ['RWPair']
import socket
import uuid

from jhsiao.ipc.sockets import sockfile
from 

class RWPair(object):
    """Read/Write file-like objects with fds.

    This can be polled for reading and can be used to interrupt polling.

    Attributes:
        rf: io.RawIOBase subclass used to read data
        wf: io.RawIOBase subclass used to write data

    For unblocking, generally a single byte should be written per event
    and a single byte should be read per event handled.
    """
    def __init__(self, sock=None):
        """Initialize.

        sock: a listening socket if provided.
            Connect to the socket to create a pair of fds.  If None, a
            random listening socket will be used.
        """
        if sock is None:
            try:
                L = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            except AttributeError:
                L = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    L.bind(('127.0.0.1', 0))
                    L.listen(1)
                    self.rf, self.wf = self._from_listener(L)
                finally:
                    L.close()
            else:
                try:
                    L.bind('\0' + uuid.uuid4().hex)
                    L.listen(1)
                    self.rf, self.wf = self._from_listener(L)
                finally:
                    L.close()
        else:
            self.rf, self.wf = self._from_listener(sock)
        self.fileno = self.rf.fileno

    def _from_listener(self, L):
        """Create a read/write file-like object from a listener socket."""
        c = socket.socket(L.family, L.type)
        c.settimeout(None)
        try:
            c.connect(L.getsockname())
        except Exception:
            c.close()
            raise
        else:
            s, a = L.accept()
            s.settimeout(None)
            return (sockfile.Sockfile(s), sockfile.Sockfile(c))

    def readinto1(self, out):
        return -2

    def fileno(self):
        return self.fileno()

    def close(self):
        self.rf.close()
        self.wf.close()

