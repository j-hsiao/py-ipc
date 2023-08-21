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
    def __init__(self, poller, exiter):
        """Initialize a ListenReader.

        listener: The raw listening socket.
        poller: A `jhsiao.ipc.polling` Poller
            Assume poller only has items registered as 'ro' or
            equivalent.  Items should also be in non-blocking mode.
        exiter: obj with fileno()
            This should already be registered with poller.
            When it becomes readable, it indicates that the thread
            should stop.
        """
        self.poller = poller
        self.cond = threading.Condition()
        self.q = []
        self.exiter = exiter
        self.thread = threading.Thread(target=self._run)

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
                            r.close()
                        else:
                            if amt > 0:
                                notify = True
                            nreading.append(r)
                    if notify:
                        cond.notify()
                reading = nreading
