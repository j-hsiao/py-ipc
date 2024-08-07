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
from __future__ import print_function

__all__ = ['Resource', 'Poller']
import collections
import io
import threading
import traceback
import sys
try:
    import errno
except ImportError:
    errno = None

EAGAIN = getattr(errno, 'EAGAIN', 11)
EWOULDBLOCK = getattr(errno, 'EWOULDBLOCK', 10035)
EINTR = getattr(errno, 'EINTR', 4)

from . import queue, rwpair

FD = 0
WRAPPED = 1
RGEN = 2
WGEN = 3
# True/False: current polling state
# None: Do not poll
RPOLL = 4
WPOLL = 5

class Resource(object):
    """Wrap a resource.

    Provide reading and writing generators.  Writing should be done
    through this wrapper class to format data into the underlying
    resource.

    _FORMAT: extend or append depending on whether format returns a single
    memoryview or a series of memoryviews
    """
    _FORMAT = 'append'
    def __init__(self, f, poller, rq):
        """Initialize a resource.

        f: a file-like object.
        poller: A Poller instance to handle this resource.
        rq: queue to put read messages into.
        """
        self.rq = rq
        self.wq = queue.Queue()
        self.pop = self.rq.pop
        self.f = f
        self.fileno = f.fileno
        self._add = getattr(self.wq.q, self._FORMAT)
        self.poller = poller
        gen = self.writegen()
        next(gen)
        self.write = gen.send

    def write(self, data):
        """Write data to resource.

        This is just a place holder and will be replaced with a
        callable.
        """
        pass


    def rprocess(self)
        """Process data read from the wrapped resource.

        This is a generator that should yield 3-tuples of
        (memoryview, currentposition, targetposition).
        The memoryview will be filled at least up to targetposition.
        The actual amount will be sent via .send()
        Parsed results should be placed into self.rq.
        """
        raise NotImplementedError

    def wprocess(self, statechanged):
        """Step through writing data from queue.

        statechanged: set of int fds that changed state.
        """
        wq = self.wq
        view = wq.peek()
        write = self.f.write
        fd = self.fileno()
        item = resources[fd]
        tot = 0
        target = len(view)
        while 1:
            try:
                amt = write(view[tot:])
            except OSError as e:
                if e.errno in (EAGAIN, EWOULDBLOCK):
                    item[WPOLL] = True
                    statechanged.add(fd)
                    yield
                elif e.errno == EINTR:
                    continue
                else:
                    traceback.print_exc()
                    item[WGEN] = item[WPOLL] = None
                    statechanged.add(fd)
                    yield
            except Exception:
                traceback.print_exc()
                item[WGEN] = item[WPOLL] = None
                statechanged.add(fd)
                yield
            else:
                if amt:
                    tot += amt
                    if target <= tot:
                        try:
                            view = wq.popnext()
                        except IndexError:
                            yield
                            view = wq.peek()
                        else:
                            yield
                        tot = 0
                        target = len(view)
                else:
                    statechanged.add(fd)
                    if amt is None:
                        item[WPOLL] = True
                    else:
                        item[WGEN] = item[WPOLL] = None
                    yield

    def format(self, data):
        """Format data into a sequence of memoryview."""
        raise NotImplementedError

    def writegen(self):
        """Use a generator
        """
        data = yield
        wq = self.wq
        q = wq.q
        hasspace = wq.hasspace:
        fd = self.fileno()
        write_ready = self.poller.write_ready
        fmt = self.format
        while 1:
            with hasspace:
                if not len(q):
                    write_ready(fd)
            self._add(fmt(data))
                data = yield


    def detach(self):
        f = self.f
        self.write = self.poller = self.f = None
        return f

TASK_REGISTER = 0
TASK_WRITE = 1
TASK_REMOVE = 2
TASK_STOP = 3
class Poller(object):
    """Polling class for handling resources.

    Incoming data is broken up into messasges.
    """
    def __init__(self, wrapper, sepq=False, on_remove=None):
        """Initialize a Poller.

        wrapper: Callable to wrap a resource.  The result should be a
            subclass of Resource.
        sepq: bool, Use separate queues per resource.  If each resource
              gets their own queue, then it is possible to wait for data
              on each individual resource but not possible to wait for
              data on any resource.  On the other hand, sharing a queue
              means it is possible to wait for any resource to have data
              ready, but cannot wait for some particular resource.
        on_remove: callable on a list, called when resource is removed.
        """
        self.thread = None
        self.lock = threading.Lock()
        self.wrapper = wrapper
        self.sepq = sepq
        if not sepq:
            self.q = queue.Queue(lock=self.lock)
        self.tasks = []
        if on_remove is None:
            self.on_remove = self._default_on_remove
        else:
            self.on_remove = on_remove

        self.rw = rwpair()
        self.thread = threading.Thread(target=self._run)
        self.thread.start()

    # ------------------------------
    # Public interface.
    # ------------------------------
    def __del__(self):
        if self.thread is not None:
            with self.lock:
                thread = self.thread
                self.thread = None
                self.tasks.append((TASK_STOP, None, None))
            thread.join()
    close = __del__

    def write_ready(self, resource):
        """Signal there is data for writing for resource."""
        if not isinstance(resource, int):
            resource = resource.fileno()
        with self.lock:
            self.tasks.append((TASK_WRITE, resource, None))
            self.rw.write(b'\n')

    def register(self, resource, write=True):
        """Register a resource with this poller.

        Return the wrapped resource.
        write: Also register the item for write polling.
               Set to False if the resource should only be
               polled for reading.
        """
        if self.sepq:
            q = queue.Queue(lock=self.lock)
        else:
            q = self.q
        wrapped = self.wrapper(resource, self, q)
        with self.lock:
            self.tasks.append((TASK_REGISTER, wrapped, write))
            self.rw.write(b'\n')
        return wrapped

    def remove(self, f):
        """Mark an fd/resource for removal from poller.

        on_remove will be called when actually removed.
        """
        fd = self._fd(f)
        with self.lock:
            self.tasks.append((TASK_REMOVE, fd, None))
            self.rw.write(b'\n')

    # ------------------------------
    # Internal interface.
    # ------------------------------
    @staticmethod
    def _default_on_remove(item):
        """Default removal callback."""
        print('removed resource', file=sys.stderr)
        print('  fd:', item[0], file=sys.stderr)

    def _fd(self f):
        if isinstance(f, int):
            return f
        else:
            return f.fileno()

    def _process_tasks_generator(self, running, resources, statechanged):
        """Generator for processing tasks."""
        rw = self.rw
        on_remove = self.on_remove
        while 1:
            with self.lock:
                tasks = self.tasks
                if tasks:
                    self.tasks = []
                else:
                    yield None
                    continue
            rw.read(len(tasks))
            for tp, thing, extra in tasks:
                if tp == TASK_REGISTER:
                    fd = thing.fileno()
                    resources[fd] = [
                        fd,
                        thing,
                        self._readit(thing, statechanged),
                        thing.wprocess(statechanged),
                        True,
                        False if extra else None,
                    ]
                elif tp == TASK_REMOVE:
                    fd = thing.fileno()
                    reading.pop(fd, None)
                    writing.pop(fd, None)
                    item = resources.pop(fd, None)
                    if item:
                        on_remove(item)

                elif tp == TASK_WRITE:
                    fd = thing.fileno()
                    writing[fd] = resources[fd][WGEN]
                elif tp == TASK_STOP:
                    del running[:]
                    yield None
                    return
            yield None

    def _readit(self, resource, statechanged):
        """Wrap a processing generator with reading.

        resource: The wrapped Resource instance.
        statechanged: set of int fds that changed state.
        """
        readinto = resource.f.readinto
        rgen = resource.rprocess()
        view, current, target = next(rgen)
        current = 0
        fd = resource.fileno()
        item = self.resources[fd]
        while 1:
            try:
                amt = readinto(view[current:])
            except OSError as e:
                if e.errno in (EAGAIN, EWOULDBLOCK):
                    item[RPOLL] = True
                    statechanged.add(fd)
                    yield
                elif e.errno == EINTR:
                    continue
                else:
                    traceback.print_exc()
                    item[RGEN] = item[RPOLL] = None
                    statechanged.add(fd)
                    yield
            except Exception:
                traceback.print_exc()
                item[RGEN] = item[RPOLL] = None
                statechanged.add(fd)
                yield
            else:
                if amt:
                    current += amt
                    if amt >= target:
                        view, current, target = rgen.send(current)
                else:
                    statechanged.add(fd)
                    if amt is None:
                        item[RPOLL] = True
                    else:
                        item[RGEN] = item[RPOLL] = None
                    yield

    def _run(self):
        """Polling thread loop."""
        reading = {}
        writing = {}
        statechanged = set()
        running = [True]
        resources = {}
        resources[self.rw.fileno()] = [
            self.rw.fileno(),
            self,
            self._process_tasks_generator(
                running, resources, statechanged)
            None,
            False,
            None
        ]
        while 1:
            for _ in reading.values():
                next(_)
            for _ in writing.values():
                next(_)

            if statechanged:
                # change state
            # poll/add to 
            #
    # ------------------------------
    # required subclass impls
    # ------------------------------
    def rwpoll(self, fd):
        """Set polling state of fd to read and write polling."""
        raise NotImplementedError

    def wpoll(self, fd):
        """Set polling state of fd to write polling."""
        raise NotImplementedError
    def rpoll(self, fd):
        """Set polling state of fd to read polling."""
        raise NotImplementedError
