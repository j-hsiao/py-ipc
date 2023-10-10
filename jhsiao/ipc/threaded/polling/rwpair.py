__all__ = ['RWPair']
import io
import socket
import uuid

from jhsiao.ipc.sockets import sockfile

class RWPair(object):
    """Read/Write file-like objects with fds.

    This can be polled for reading and can be used to interrupt polling.

    Attributes:
        rf: io.RawIOBase subclass used to read data
        wf: io.RawIOBase subclass used to write data

    For unblocking, generally a single byte should be written per event
    and a single byte should be read per event handled.
    """
    def __init__(self, sock=None, buffered=False):
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
                addr = ('127.0.0.1', 0)
            else:
                addr = '\0' + uuid.uuid4().hex
            try:
                L.bind(addr)
                L.listen(1)
                self.rf, self.wf = self._from_listener(L)
            finally:
                L.close()
        else:
            self.rf, self.wf = self._from_listener(sock)
        if buffered:
            self.rf = io.BufferedReader(self.rf)
            self.wf = io.BufferedWriter(self.wf)
        self.fileno = self.rf.fileno
        self.write = self.wf.write
        self.read = self.rf.read
        self.readinto = self.rf.readinto
        self.flush = self.wf.flush

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

    def fileno(self):
        return self.fileno()

    def close(self):
        self.rf.close()
        self.wf.close()

