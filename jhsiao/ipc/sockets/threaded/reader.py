"""Read messages from multiple sockets in a single thread."""
__all__ = ['Reader']
import threading
import sys

if sys.version_info.major > 2:
    _wait_for_cond = threading.Condition.wait_for
else:
    import time
    def _wait_for_cond(cond, pred, timeout=None):
        """Wait for pred to be true.

        Assume cond is held before this is called.
        """
        if pred():
            return True
        if timeout is None:
            while not pred():
                cond.wait(None)
            return True
        elif timeout == 0:
            return False
        else:
            end = time.time() + timeout
            cond.wait(timeout)
            now = time.time()
            while not pred():
                if now < end:
                    cond.wait(end - now)
                    now = time.time()
                else:
                    return False
            return True

class Reader(object):
    """Wrap a poller and read completed messages."""
    def __init__(self, poller, wrappercls):
        """Initialize a ListenReader.

        listener: The raw listening socket.
        poller: A `jhsiao.ipc.polling` Poller
        wrappercls: A class to wrap incoming socket.
        """
        self.poller = poller
        self.cond = threading.Condition()
        self.q = []

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

    def _run(self):
        """Continually poll for new data.

        When messages are completed, add to self.q
        """
        # TODO
