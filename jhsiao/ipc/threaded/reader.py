"""Read messages from multiple sockets in a single thread."""
from __future__ import print_function

__all__ = ['Reader']
import threading
import sys

from ..formats import bases

from . import polling
from .polling import control


class Reader(object):
    """Most basic read polling."""

    class Control(control.RWPair):
        def __init__(self, reader):
            super(Control, self).__init__()
            self.reader = reader

        def readinto1(self, out):
            del self.reader.running[:]
            return -2

    def __init__(self, poller, verbose=False, daemon=False):
        """Initialize a ListenReader.

        poller: A `jhsiao.ipc.sockets.threaded.polling` RPoller
        """
        self.poller = poller
        self._ctrl = self.Control(self)
        self.poller.register(self._ctrl, 'r')
        self.verbose = verbose
        self.cond = threading.Condition()
        self.q = []
        self.running = [1]
        self.thread = threading.Thread(target=self._run)
        self.thread.daemon = daemon

    def _predicate(self):
        return self.q

    def get(self, timeout=None):
        """Get any pending messages."""
        with self.cond:
            if (not self.q and
                    not _wait_for_cond(
                        self.cond, self._predicate, timeout)):
                return []
            ret = self.q
            self.q = []
            return ret

    def start(self):
        self.thread.start()

    def stop(self, closeitems=True):
        """Stop the thread.

        Any registered items will be stored in self.items attr.
        """
        if self.thread is not None:
            self._ctrl.set()
            self.thread.join()
            self._ctrl.close()
            self.thread = None
            if closeitems:
                for item in self.items:
                    item.close()

    def _run(self):
        """Poll and read in new data to self.q."""
        reading = []
        poller = self.poller
        cond = self.cond
        bad = []
        running = self.running
        try:
            while running:
                result = poller.poll(0) if reading else poller.poll()
                with self.cond:
                    L1 = len(self.q)
                    poller.fill(result, reading, self.q, bad)
                    if len(self.q) != L1:
                        self.cond.notify()
                if bad:
                    for item in bad:
                        if self.verbose:
                            print('Closed fd {}'.format(r.fileno()), file=sys.stderr)
                        item.close()
        finally:
            self.items = [item for item in poller if item is not self._ctrl]
            self.poller.close()

class SocketListener(Reader):
    def __init__(self, addr=None, sock=None):
        """Initialize SocketListener.

        addr: address to connect to.
        sock: the socket to use.

        If sock is given, then use it.
        Otherwise, bind to addr.
        """
        pass
