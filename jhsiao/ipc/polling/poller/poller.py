"""Generic poller interface.

Resources will be wrapped in generator expressions for handling.
In general, when polling, the fewer results, the better for performance.
This is regardless of what polling mechanism is used. (poll, epoll,
select, others not yet tested.) As a result, adopt epoll one-shot like
behavior.  Objects for reading are assumed to be readable until
EWOULDBLOCK or EAGAIN or any other equivalent result.  Likewise, objects
are assumed to be writeable until EWOULDBLOCK or EAGAIN, etc.

impls:
1. poller only polls for readable/writable.
   call next() on each readable/writable.
   iterable modifies poller, making appropriate changes.

2. Readers yield read requests.  Poller handles read request appropriately
   when done, then send result to reader and get the new read request.


"""
import traceback
import threading
try:
    import errno
except ImportError:
    errno = None

EAGAIN = getattr(errno, 'EAGAIN', 11)
EWOULDBLOCK = getattr(errno, 'EWOULDBLOCK', 10035)
EINTR = getattr(errno, 'EINTR', 4)

from . import rwpair

FD = 0
OBJ = 1
RGEN = 2
WGEN = 3
WRITER = 4
RPOLL = 5
WPOLL = 6

class Poller(object):
    """Poll resources and handle io.

    Readers are assumed to have no data available until polled
    otherwise.  Writers are assumed to be writable until polled
    otherwise.
    """
    def __init__(self, rgen, wgen):
        """Initialize a poller.

        rgen, wgen: func(poller, resource).
            These should return generators that can be stepped through
            with next().
        """
        self.control = rwpair.RWPair()
        self.running = False
        self.resources = {}
        self.rpending = {}
        self.wpending = {}
        self.statechanged = set()
        self.out = []
        self.rgen = rgen
        self.wgen = wgen
        self._tasks = []
        self.lock = threading.Lock()

    def __iter__(self):
        """Handle tasks."""
        lck = self.lock
        while 1:
            with lck:
                self.control.read(len(self._tasks))
                tasks = self._tasks
                self._tasks = []
            for task in self._tasks:
                try:
                    task[0](*task[1:])
                except Exception:
                    if task is None:
                        self.running = False
                        break
                    else:
                        traceback.print_exc()
            yield

    def rpoll(self, fd):
        """(re)Register for read-only polling."""
        raise NotImplementedError
    def wpoll(self, fd):
        """(re)Register for write-only polling."""
        raise NotImplementedError
    def rwpoll(self, fd):
        """(re)Register for read and write polling."""
        raise NotImplementedError
    def nopoll(self, fd):
        """(re)Register for no polling."""
        raise NotImplementedError

    def wrap(self, fd, resource):
        """Wrap a resource.

        Return [
            0: fileno: int, the file number.
            1: resource: the object.
            2: rgenerator: generator, next() should read and process a bit.
            3: wgenerator: generator, next() should write a bit.
            4: writer wrapper
            5: rpolling: bool, whether object should be read polled.
            6: wpolling: bool, whether object should be write polled.
        ]
        """
        wgen = self.wgen(self, resource)
        return [
            fd, resource,
            iter(self.rgen(self, resource)),
            iter(wgen), wgen,
            True, False]

    def register(self, resource, read=True):
        """Add an item to poller threadsafe.

        resource: should have fileno(), readinto(), and write() methods.
        read: bool, begin read-polling.
        Return a wrapped object.  Writing should use that object.
        """
        fd = resource.fileno()
        with self.lock:
            self.control.write(b' ')
            self._tasks.append((self.add, resource, read))

    def unregister(self, resource):
        """Remove an item from poller threadsafe."""
        if not isinstance(resource, int):
            resource = resource.fileno()
        with self.lock:
            self.control.write(b' ')
            self._tasks.append((self.remove, resource))

    def add(self, resource, read=True):
        """Add a resource for handling.

        This should be called from same thread as the polling thread.
        resource: file-like object, the resource to add, should be
                  non-blocking.

        Added resources will be added to read polling only.
        When writing is required, then it will be added to self.writers
        and polled as necessary.
        """
        fd = resource.fileno()
        orig = self.resources.pop(fd, None)
        if orig is not None:
            self.remove(fd)
        wrapped = self.resources[fd] = self.wrap(fd, resource)

    def remove(self, fd):
        """Unregister from poller.

        This should be called from same thread as the polling thread.
        """
        self.rpending.pop(fd, None)
        self.wpending.pop(fd, None)
        self.resources.pop(fd, None)

    def step(self):
        """Poll registered resources and handle a little bit."""
        for item in self.rpending.values():
            next(item)
        for item in self.wpending.values():
            next(item)
        for fd in self.statechanged:
            info = self.resources[fd]
            if info[RPOLL]:
                if info[WPOLL]:
                    self.rpending.pop(fd, None)
                    self.wpending.pop(fd, None)
                    self.rwpoll(fd)
                else:
                    self.rpending.pop(fd, None)
                    self.rpoll(fd)
            elif info[WPOLL]:
                self.wpending.pop(fd, None)
                self.wpoll(fd)
            else:
                if info[RPOLL] is None and info[WPOLL] is None:
                    self.remove(fd)
        self.statechanged.clear()

    def run(self):
        """Run polling loop."""
        self.running = True
        while self.running:
            self.step()

    def start(self):
        """Start polling loop in a separate thread."""
        self.thread = threading.Thread(target=self.run)
        self.thread.start()

    def stop(self):
        """Stop polling thread."""
        with self.lock:
            self.control.write(b'0')
            self._tasks.append(None)
        self.thread.join()

    def __del__(self):
        self.close()

    def close(self):
        self.resources.clear()
        self.rpending.clear()
        self.wpending.clear()
        self.stop()
        self.control.close()

    def readinto(self, fd, readinto, buf):
        """A generator to read until buf is full.

        Handle the appropriate resource manipulations.
        1. If EOF is encountered, remove from rpending.
        2. If EAGAIN/EWOULDBLOCK, remove from rpending and
           begin read polling.
        3. Otherwise, no state change, last yield is the total number
           of bytes read.
        """
        target = len(buf)
        total = 0
        v = memoryview(buf)
        while 1:
            try:
                amt = readinto(v)
            except OSError as e:
                if e.errno in (EWOULDBLOCK, EAGAIN):
                    self.statechanged.add(fd)
                    self.resources[fd][RPOLL] = True
                    yield
                elif e.errno == EINTR:
                    continue
                else:
                    self.statechanged.add(fd)
                    self.resources[fd][RPOLL] = None
                    yield -1
                    return
            else:
                if amt:
                    total += amt
                    if total == target:
                        yield total
                        return
                    v = v[amt:]
                    yield 0
                else:
                    self.statechanged.add(fd)
                    self.resources[fd][RPOLL] = None
                    yield -1
                    return




class Poller2(object):
    """Poll resources and handle io.

    Readers are assumed to have no data available until polled
    otherwise.  Writers are assumed to be writable until polled
    otherwise.
    """

    def __init__(self, rgen, wgen):
        """Initialize.

        rgen: generator for reading.  Yield buffers for the poller to
              read data into.
        wgen: generator for writing. Yield data to write.
        """
        self.control = rwpair.RWPair()
        self.running = False
        self.resources = {}
        self.rpending = {}
        self.wpending = {}
        self.statechanged = set()
        self.out = []
        self.rgen = rgen
        self.wgen = wgen
        self._tasks = []
        self.lock = threading.Lock()

    def register(self, resource, read=True):
        """Add an item to poller threadsafe.

        resource: should have fileno(), readinto(), and write() methods.
        read: bool, begin read-polling.
        Return a wrapped object.  Writing should use that object.
        """
        fd = resource.fileno()
        with self.lock:
            self.control.write(b' ')
            self._tasks.append((self.add, resource, read))

    def unregister(self, resource):
        """Remove an item from poller threadsafe."""
        if not isinstance(resource, int):
            resource = resource.fileno()
        with self.lock:
            self.control.write(b' ')
            self._tasks.append((self.remove, resource))


    def __iter__(self):
        """Handle tasks."""
        lck = self.lock
        while 1:
            with lck:
                self.control.read(len(self._tasks))
                tasks = self._tasks
                self._tasks = []
            for task in self._tasks:
                try:
                    task[0](*task[1:])
                except Exception:
                    if task is None:
                        self.running = False
                        break
                    else:
                        traceback.print_exc()
            yield

    def rpoll(self, fd):
        """(re)Register for read-only polling."""
        raise NotImplementedError
    def wpoll(self, fd):
        """(re)Register for write-only polling."""
        raise NotImplementedError
    def rwpoll(self, fd):
        """(re)Register for read and write polling."""
        raise NotImplementedError
    def nopoll(self, fd):
        """(re)Register for no polling."""
        raise NotImplementedError

    def wrap(self, fd, resource):
        """Wrap a resource.

        Return [
            0: fileno: int, the file number.
            1: resource: the object.
            2: rgenerator: generator, next() should read and process a bit.
            3: wgenerator: generator, next() should write a bit.
            4: writer wrapper
            5: rpolling: bool, whether object should be read polled.
            6: wpolling: bool, whether object should be write polled.
        ]
        """
        wgen = self.wgen(self, resource)
        return [
            fd, resource,
            iter(self.rgen(self, resource)),
            iter(wgen), wgen,
            True, False]

    def add(self, resource, read=True):
        """Add a resource for handling.

        This should be called from same thread as the polling thread.
        resource: file-like object, the resource to add, should be
                  non-blocking.

        Added resources will be added to read polling only.
        When writing is required, then it will be added to self.writers
        and polled as necessary.
        """
        fd = resource.fileno()
        orig = self.resources.pop(fd, None)
        if orig is not None:
            self.remove(fd)
        wrapped = self.resources[fd] = self.wrap(fd, resource)

    def remove(self, fd):
        """Unregister from poller.

        This should be called from same thread as the polling thread.
        """
        self.rpending.pop(fd, None)
        self.wpending.pop(fd, None)
        self.resources.pop(fd, None)

    def step(self):
        """Poll registered resources and handle a little bit."""
        changed = set()
        for item in self.rpending.values():
            fd, gen, readinto, buf, target = item
            try:
                amt = readinto(buf)
            except OSError as e:
                if e.errno in (EWOULDBLOCK, EAGAIN):
                    #TODO poll
                    pass
                elif e.errno in EINTR:
                    pass
                else:
                    #TODO no poll remove from read
                    pass
            else:
                if amt:
                    if target <= amt:
                        pass
                    else:
                        target -= amt
                else:
                    if amt is None:
                        #TODO back to poll
                        pass
                    else:
                        #TODO no poll remove from read
                        pass
