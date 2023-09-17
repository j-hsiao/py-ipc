"""FD for control of polling.

Polling is done in blocking manner.  As a result, it must be interrupted
to add/remove fds for polling.  These use a fd that should be polled for
reading (not oneshot)  readinto1 should return -2 for all these classes.
"""
from __future__ import print_function
__all__ = ['RWPair', 'PollRegister', 'PollWrapListener']
import socket
import sys
import uuid
import traceback

from ... import sockfile
from ...formats import bases

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


class NullLock(object):
    def __enter__(self):
        pass
    def __exit__(self, tp, exc, tb):
        pass

class PollWrapListener(object):
    """Wrap accepted connections and register with a poller."""
    def __init__(
        self, listener, poller, wrapcls,
        wrapmode='r', pollmode='ro', verbose=False, timeout=0):
        """Initialize a PollWrapListener.

        listener: A listening socket.
            The socket to listen on to accept connections.
        poller: A Poller from `jhsiao.ipc.polling`.
            The poller to register accepted connections with.
        wrapcls: callable
            Wrap the accepted connections.  Should expect a file-like
            object (sockfile.Sockfile).
        wrapmode: str
            The mode to use for sockfile.Sockfile wrapping the socket.
        pollmode: str or int
            The mode to use when registering connections.
        verbose: bool
            Verbose when accepting or error.
        timeout: float or None
            Set accepted connection timeout.
        """
        self.listener = listener
        self.timeout = timeout
        self.verbose = verbose
        self.poller = poller
        self.pollmode = pollmode
        self.wrapmode = wrapmode
        self.wrapcls = wrapcls

    def __getattr__(self, name):
        thing = getattr(self.listener, name)
        if callable(thing):
            setattr(self, name, thing)
        return thing

    def readinto1(self, out):
        s, a = self.listener.accept()
        s.settimeout(self.timeout)
        self.poller.register(
            self.wrapcls(sockfile.Sockfile(s, self.wrapmode)),
            self.pollmode)
        if self.verbose:
            print(
                'Accepted connection from', a,
                'fd', s.fileno(),
                file=sys.stderr)
        return -2

class ReadRegister(object)


# TODO:
# class for handling
# read/write or readonly/writeonly etc
# class needs access to:
# r, w, bad? poller, items?
