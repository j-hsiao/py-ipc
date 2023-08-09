__all__ = ['Listener']
import socket

from jhsiao.ipc.sockets import util

class Listener(object):
    """Wrap a listening socket.

    Set some options before returning accepted connections.
    """
    def __init__(self, sock, cloexec=True, nodelay=False, timeout=None):
        self.sock = sock
        self._cloexec = cloexec
        self._nodelay = nodelay
        self._timeout = timeout
    def __getattr__(self, name):
        val = getattr(self.sock, name)
        if callable(val):
            setattr(self, name, val)
        return val
    def accept(self, cloexec=None, nodelay=None, timeout=Ellipsis):
        """Returns accepted socket and address.

        Additionally sets cloexec and nodelay if applicable.
        """
        s, a = self.sock.accept()
        util.set_cloexec(s, self._cloexec if cloexec is None else cloexec)
        if s.type == socket.SOCK_STREAM:
            if nodelay is None:
                nodelay = self._nodelay
            s.setsockopt(
                socket.IPPROTO_TCP, socket.TCP_NODELAY, int(nodelay))
        s.settimeout(self._timeout if timeout is Ellipsis else timeout)
        return s, a
