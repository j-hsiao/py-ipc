"""Listening socket as reading.


"""
from __future__ import print_function
import sys
import traceback

from jhsiao.ipc.sockets.formats import bases

class ListenerReader(object):
    """Wrap a listening socket to match reader interface."""
    def __init__(self, listener, verbose=False, timeout=0):
        """Initialize a ListenReader.

        listener: A listening socket.
            The listener's timeout should already be set.
            It can probably be ssl wrapped, though not tested.
        poller: A `jhsiao.ipc.polling` Poller.
            Accepted sockets will be registered with the poller.
        wrappercls: A class to wrap incoming socket.
        verbose: bool
            Print errors and accepting sockets.
        timeout: float or None
            Set accepted connection timeout.
        """
        self.listener = listener
        self.timeout = timeout
        self.verbose = verbose

    def __getattr__(self, name):
        thing = getattr(self.listener, name)
        if callable(thing):
            setattr(self, name, thing)
        return thing

    def readinto1(self, out):
        """Accept a single connection.

        Match the same readinto1 interface as
            `jhsiao.ipc.sockets.formats.bases.Reader`.
        Always return None to indicate that it should continue
        to be polled.
        """
        try:
            s, a = self.listener.accept()
            s.settimeout(self.timeout)
            self.accept_connection(s)
            if self.verbose:
                print(
                    'Accepted connection from', a,
                    'fd', s.fileno(),
                    file=sys.stderr)
        except OSError as e:
            if e.errno in bases.WOULDBLOCK:
                return None
        return None
    readinto = readinto1

    def read(self):
        self.readinto1(None)
        return []

    def accept_connection(self, s):
        """Accept a connection.

        s: The accepted socket.

        Default implementation just closes it.
        """
        s.close()


class PollWrapListener(ListenerReader):
    """Wrap accepted connections and register with a poller."""
    def __init__(
        self, listener, poller, wrapcls,
        mode='ro', verbose=False, timeout=0):
        """Initialize a PollWrapListener.

        listener: A listening socket.
            The socket to listen on to accept connections.
        poller: A Poller from `jhsiao.ipc.polling`.
            The poller to register accepted connections with.
        wrapcls: callable
            Wrap the accepted connections.
        mode: str or int
            The mode to use when registering connections.
        verbose: bool
            Verbose when accepting or error.
        timeout: float or None
            Set accepted connection timeout.
        """
        super(PollWrapListener, self).__init__(
            listener, verbose, timeout)
        self.poller = poller
        self.mode = mode
        self.wrapcls = wrapcls

    def accept_connection(self, s):
        self.poller.register(self.wrapcls(s), self.mode)
