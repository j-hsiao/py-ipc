"""Read from sockets."""

class ListenReader(object):
    """Wrap a listening socket to match reader interface."""
    def __init__(self, listener, poller, wrappercls):
        """Initialize a ListenReader.

        listener: The raw listening socket.
        poller: A `jhsiao.ipc.polling` Poller
        wrappercls: A class to wrap incoming socket.
        """
        self.listener = listener
        self.poller = poller
        self.listener.settimeout()

    def readinto1(self, out):
        
