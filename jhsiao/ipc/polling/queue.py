"""Queue implementation that can share mutex.

If each resource should have its own queue, then using the built-in
queue implementation would have a separate mutex per resource which is
potentially many.  Instead, there is generally only a need for 1 lock
since processing happens in a single thread with polling anyways.

In general, locks might have an os upper limit, but I haven't found any
sources that suggest condition variables also have an upper limit.
"""
import collections
import threading
try:
    import queue
except ImportError:
    import Queue as queue

try:
    from errno import EINTR
except ImportError:
    EINTR = 4

try:
    wait_for = threading.Condition.wait_for
except AttributeError:
    def wait_for(cond, pred, timeout=None):
        """Wait for a predicate."""
        result = pred()
        if result or timeout == 0:
            return result
        elif timeout is None:
            while 1:
                try:
                    cond.wait()
                except EnvironmentError as e:
                    if e.errno != EINTR:
                        raise
                if pred():
                    return True
        else:
            end = time.time() + timeout
            while 1:
                try:
                    cond.wait(timeout)
                except EnvironmentError as e:
                    if e.errno != EINTR:
                        raise
                if pred():
                    return True
                now = time.time()
                if end <= now:
                    return False
                timeout = end - now

class Queue(object):
    """A queue that also takes a lock as argument."""
    def __init__(self, maxsize=0, lock=None):
        if maxsize > 0:
            self.maxsize = maxsize
        else:
            self.maxsize = float('inf')
        self.q = collections.deque()
        if lock is None:
            self.lock = threading.Lock()
        else:
            self.lock = lock
        self.hasdata = threading.Condition(self.lock)
        self.hasspace = threading.Condition(self.lock)

    def qsize(self):
        with self.lock:
            return len(self.q)

    def _hasdata(self):
        return len(self.q) > 0

    def _hasspace(self):
        return len(self.q) < self.maxsize

    def push(self, item, timeout=None):
        """Add an item to queue.

        Timeout if no space.
        """
        hasspace = self.hasspace
        with hasspace:
            if wait_for(hasspace, self._hasspace, timeout):
                self.q.append(item)
            else:
                raise queue.Full

    def pop(self, timeout=None):
        """Remove an item from queue.

        Timeout if no objects.
        """
        hasdata = self.hasdata
        with hasdata:
            if wait_for(hasdata, self._hasdata, timeout):
                return self.q.popleft()
            else:
                raise queue.Empty
