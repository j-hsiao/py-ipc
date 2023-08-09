"""Use a socket as a io.RawIOBase."""
__all__ = ['Sockfile']
import io
import socket

class Sockfile(io.RawIOBase):
    """Wrap a socket in a file-like object.

    NOTE: non-blocking mode is not supported.  If you do not want to
    block, then use polling/select.

    shutdown observations:
        SHUT_RD: this side will return b'' whenever calling receive and
            no data is available.  The otherside can still write data
            and this side will receive it.

        SHUT_WR: This side can no longer write data.
                 The Other side will receive b'' whenever reading data.

        If SHUT_RD and SHUT_WR, connection seems to be auto-broken.  ie
        if SHUT_RD, receive data until SHUT_WR, after which connection
        is broken. (Though fd still exists.)

    Class methods should work, but may be overwritten for each instance
    for slightly better performance.
    """
    SHUT_RD = socket.SHUT_RD
    SHUT_WR = socket.SHUT_WR
    SHUT_RDWR = socket.SHUT_RDWR
    def __init__(self, sock, mode = 'rwb'):
        """Wrap a socket.

        sock: socket to wrap
        mode: mode, determines whether read() or write() are available.
            Also determines the default for self.shutdown(). b is ignored.
            Sockfile is always binary.
        """
        super(Sockfile, self).__init__()
        self.socket = sock
        self._w = bool(set('wa+').intersection(mode))
        self._r = bool(set('r+').intersection(mode))
        if not (self._w or self._r):
            raise ValueError('Mode must be at least read or write.')
        FLAGS = ''
        if self._r:
            FLAGS ='RD'
            self.readinto = sock.recv_into
        if self._w:
            FLAGS += 'WR'
            self.write = sock.send
        self._shut = getattr(socket, 'SHUT_{}'.format(FLAGS))
        self.fileno = sock.fileno
        self._name = None

    def __getattr__(self, attr):
        try:
            creator = object.__getattribute__(self, '_' + attr)
        except AttributeError:
            raise AttributeError(attr)
        else:
            try:
                result = creator()
            except Exception:
                raise AttributeError(attr)
            else:
                setattr(self, attr, result)
                return result

    def _name(self):
        """Return peer name."""
        try:
            return self.socket.getpeername()
        except Exception:
            try:
                return '"bad socket fd{}"'.format(self.fileno())
            except Exception:
                return '"bad socket id{}"'.format(id(self))

    def shutdown(self, method=None):
        """Shutdown the the wrapped socket.

        Method can be socket.SHUT_[RD|WR|RDWR]
        If None, then method will default to RD, WR or RDWR
        depending on whether the Sockfile was opened with
        read-only, write-only or read and write modes.
        """
        if method is None:
            method = self._shut
        try:
            self.socket.shutdown(method)
        except Exception:
            pass

    def detach(self):
        """Detach from the wrapped socket.

        Set closed state and return the wrapped socket.
        """
        if self.socket is not None:
            io.RawIOBase.close(self)
            ret = self.socket
            self.socket = None
            if self._w:
                del self.write
            if self._r:
                del self.readinto
            del self.fileno
            return ret

    #IOBase
    def close(self):
        """Close socket."""
        if self.socket is not None:
            self.shutdown(socket.SHUT_RDWR)
            self.detach().close()
    def fileno(self):
        return self.socket.fileno()
    def flush(self):
        pass
    def isatty(self):
        return False
    def readable(self):
        return self._r
    # readline and readlines are free by defining readinto()

    def seekable(self):
        return False
    def seek(self, *args):
        raise io.UnsupportedOperation("sockfile cannot seek")
    def tell(self):
        raise io.UnsupportedOperation("Position not tracked.")
    def truncate(self):
        raise io.UnsupportedOperation("sockfile cannot seek")

    # writelines free by defining write()
    def writable(self):
        return self._w

    # RawIOBase

    # read, readall is free by defining readinto
    def readinto(self, buf):
        """Read data into buf, max 1 syscall."""
        return self.socket.recv_into(buf)

    def write(self, data):
        """Write some data.  Return amount written."""
        return self.socket.send(data)
