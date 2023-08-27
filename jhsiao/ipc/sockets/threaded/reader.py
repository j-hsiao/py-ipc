"""Read messages from multiple sockets in a single thread."""
from __future__ import print_function

__all__ = ['Reader']
import threading
import sys

from ..formats import bases

if sys.version_info > (3,4):
    _wait_for_cond = threading.Condition.wait_for
else:
    import time
    def _wait_for_cond(cond, pred, timeout=None):
        """Wait for pred to be true.

        Assume cond is held before this is called.
        """
        result = pred()
        if result or timeout == 0:
            return result
        elif timeout is None:
            while not pred():
                cond.wait(None)
            return True
        else:
            end = time.time() + timeout
            cond.wait(timeout)
            while not pred():
                now = time.time()
                if now < end:
                    try:
                        cond.wait(end - now)
                    except EnvironmentError as e:
                        if e.errno != bases.EINTR:
                            raise
                else:
                    return False
            return True

class Reader(object):
    """Wrap a poller and read completed messages."""
    def __init__(self, poller, verbose=False):
        """Initialize a ListenReader.

        listener: The raw listening socket.
        poller: A `jhsiao.ipc.sockets.threaded.polling` RPoller
        """
        self.poller = poller
        self.cond = threading.Condition()
        self.q = []
        self.exiter = exiter
        self.thread = threading.Thread(target=self._run)
        self.verbose = verbose

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

    def join(self):
        self.thread.join()

    def _run(self):
        """Continually poll for new data.

        When messages are completed, add to self.q
        """
        exiter = self.exiter
        reading = []
        poller = self.poller
        rearm = poller.r | poller.o
        cond = self.cond
        isselect = poller.backend == 'select'
        while 1:
            if isselect:
                reading.extend(poller.poll(0 if reading else None)[0])
            else:
                reading.extend(poller.anypoll(0 if reading else None))
            if reading:
                nreading = []
                with cond:
                    q = self.q
                    notify = False
                    for r in reading:
                        if r is exiter:
                            return
                        amt = r.readinto1(q)
                        if amt is None:
                            poller.register(r, rearm)
                        elif amt < 0:
                            if self.verbose:
                                print('Closed fd {}'.format(r.fileno()), file=sys.stderr)
                            r.close()
                        else:
                            if amt > 0:
                                notify = True
                            nreading.append(r)
                    if notify:
                        cond.notify()
                reading = nreading
