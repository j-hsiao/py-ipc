"""Generic poller interface.

Resources will be wrapped in generator expressions for handling.
In general, when polling, the fewer results, the better for performance.
This is regardless of what polling mechanism is used. (poll, epoll,
select, others not yet tested.) As a result, adopt epoll one-shot like
behavior.  Objects for reading are assumed to be readable until
EWOULDBLOCK or EAGAIN or any other equivalent result.  Likewise, objects
are assumed to be writeable until EWOULDBLOCK or EAGAIN, etc.
Resources should thus be in non-blocking mode.

"""
__all__ = ['Resource', 'Poller']
import collections
import io
import threading
import traceback
try:
    import errno
except ImportError:
    errno = None

EAGAIN = getattr(errno, 'EAGAIN', 11)
EWOULDBLOCK = getattr(errno, 'EWOULDBLOCK', 10035)
EINTR = getattr(errno, 'EINTR', 4)

from . import queue, rwpair


FD = 0
OBJ = 1
RGEN = 2
WGEN = 3
WRAPPED = 4
RPOLL = 5
WPOLL = 6

class Resource(object):
    """Wrap a resource."""
    def __init__(self, f, poller, rq):
        """Initialize a resource.

        f: a file-like object.
        poller: A Poller instance to handle this resource.
        """
        self.rq = rq
        self.wq = collections.deque()
        self.pop = self.rq.pop
        self.f = f
        self.fileno = f.fileno

    def rprocess(self, poller)
        """Process data read from the wrapped resource.

        Parsed results should be placed into self.rq.
        """
        raise NotImplementedError

    def write(self):
        # TODO: write and process data,
        # then throw to poller to do the actual sending?
        pass


TASK_REGISTER = 0
TASK_WRITE = 1
class Poller(object):
    """Polling class for handling resources.

    Incoming data is broken up into messasges.
    """
    def __init__(self, wrapper, sepq=False):
        """Initialize a Poller.

        wrapper: Callable to wrap a resource.  The result should be a
            subclass of Resource.
        sepq: bool, Use separate queues per resource.  If each resource
              gets their own queue, then it is possible to wait for data
              on each individual resource but not possible to wait for
              data on any resource.  On the other hand, sharing a queue
              means it is possible to wait for any resource to have data
              ready, but cannot wait for some particular resource.
        """
        self.lock = threading.Lock()
        self.wrapper = wrapper
        self.resources = {}
        self.sepq = sepq
        if not sepq:
            self.q = queue.Queue(lock=self.lock)
        self.tasks = [], []
        self.rw = rwpair()

    # ------------------------------
    # Public interface.
    # ------------------------------
    def send(self, resource, data):
        """Enqueue data to be sent."""
        with self.lock:
            self.tasks[TASK_WRITE].append((resource, data))

    def register(self, resource):
        """Register a resource with this poller.

        Return the wrapped resource.
        """
        if sepq:
            q = queue.Queue(lock=self.lock)
        else:
            q = self.q
        wrapped = self.wrapper(resource, self, q)
        with self.lock:
            self.tasks[TASK_REGISTER].append(wrapped)
        return wrapped

    # ------------------------------
    # Internal interface.
    # ------------------------------
