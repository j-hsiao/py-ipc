"""Use a socket as a io.RawIOBase."""
__all__ = ['Sockfile']
import functools
import io
import socket
import sys
import platform

try:
    import errno
except ImportError:
    EAGAIN = 11
    EWOULDBLOCK = 10035 if platform.system() == 'Windows' else 11
else:
    EAGAIN = getattr(errno, 'EAGAIN', 11)
    EWOULDBLOCK = getattr(
        errno,
        'EWOULDBLOCK',
        10035 if platform.system() == 'Windows' else 11)

class Sockfile(io.RawIOBase):
    """Wrap a socket in a file-like object.

    shutdown observations:
        SHUT_RD: this side will return b'' whenever calling receive and
            no data is available.  The otherside can still write data
            and this side will receive it.

        SHUT_WR: This side can no longer write data.
                 The Other side will receive b'' whenever reading data.

        If SHUT_RD and SHUT_WR, connection seems to be auto-broken.  ie
        if SHUT_RD, receive data until SHUT_WR, after which connection
        is broken. (Though fd still exists.)
    """
    SHUT_RD = socket.SHUT_RD
    SHUT_WR = socket.SHUT_WR
    SHUT_RDWR = socket.SHUT_RDWR
    def __init__(self, sock, mode = 'rwb'):
        """Wrap a socket.

        sock: socket to wrap
        mode: mode, determines whether read() or write() are available.
            Also determines the default for self.shutdown()
        """
        super(Sockfile, self).__init__()
        self.socket = sock
        if 'b' not in mode:
            print(
                'WARNING: Sockfile only handles binary io but b not present in mode',
                file=sys.stderr)
        self._w = bool(set('wa+').intersection(mode))
        self._r = bool(set('r+').intersection(mode))
        if not (self._w or self._r):
            raise Exception("Sockfile neither read nor write")
        FLAGS = ''
        if self._r:
            FLAGS ='RD'
            self._read = self._block_to_none(sock.recv)
            self._readinto = self._block_to_none(sock.recv_into)
            self._rpos = 0
        if self._w:
            FLAGS += 'WR'
            self._write = self._block_to_none(sock.send)
            self._wpos = 0
        self._shut = getattr(socket, 'SHUT_{}'.format(FLAGS))
        self.fileno = sock.fileno
        self._name = None

    @property
    def name(self):
        """Some identifier, str if unix, tup if inet."""
        if self._name is None:
            try:
                self._name = self.socket.getpeername()
            except Exception:
                try:
                    self._name = '"bad socket fd{}"'.format(self.fileno())
                except Exception:
                    self._name = '"bad socket"'
        return self._name

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

        Set closed state and return the wrapped socket. Note however
        that some internal references may still point to the socket
        so calling any functions after detaching is undefined.
        """
        io.RawIOBase.close(self)
        ret = self.socket
        self.socket = None
        return ret

    #IOBase
    def close(self):
        """Close socket."""
        if self.socket is not None:
            self.shutdown(socket.SHUT_RDWR)
            self.detach().close()
    # fileno = socket.fileno()
    def flush(self):
        pass
    def isatty(self):
        return False
    def readable(self):
        return self._r
    # readline and readlines are free by defining read()

    def seekable(self):
        return False
    def seek(self, *args):
        raise io.UnsupportedOperation("sockfile cannot seek")
    def tell(self):
        """Return position.

        If readable, return number of bytes read from initialization.
        Otherwise, return number of bytes written from initizliation.
        """
        if self._r:
            return self._rpos
        return self._wpos
    def rtell(self):
        """Total number of bytes read so far."""
        return self._rpos
    def wtell(self):
        """Total bytes written so far."""
        return self._wpos
    def truncate(self):
        raise io.UnsupportedOperation("sockfile cannot seek")

    # writelines
    def writable(self):
        return self._w

    @staticmethod
    def _block_to_none(func):
        """Convert socket timeout and EAGAIN, EWOULDBLOCK to None."""
        @functools.wraps(func)
        def wrap(arg):
            try:
                return func(arg)
            except socket.timeout:
                return None
            except EnvironmentError as e:
                if e.errno in (EAGAIN, EWOULDBLOCK):
                    return None
                raise
        return wrap
    # RawIOBase
    def _read(self, amt=-1):
        raise io.UnsupportedOperation('read')

    def read(self, amt=-1):
        if amt is None or amt < 0:
            ret = self.readall()
        else:
            ret = self._read(amt)
        if ret:
            self._rpos += len(ret)
        return ret

    def readinto(self, buf):
        amt = self._readinto(buf)
        if amt:
            self._rpos += amt
        return amt

    def _write(self, data):
        raise io.UnsupportedOperation('write')
    def write(self, data):
        ret = self._write(data)
        if ret:
            self._wpos += ret
        return ret
