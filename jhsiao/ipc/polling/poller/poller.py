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

from . import rwpair

try:
    wait_for = threading.Condition.wait_for
except AttributeError:
    def wait_for(cond, pred, timeout=None):
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

FD = 0
OBJ = 1
RGEN = 2
WGEN = 3
WRAPPED = 4
RPOLL = 5
WPOLL = 6

def default_handler(poller, info, reason=None):
    """Handle error on info.

    This is called after info read and write both error out and the
    object is removed from polling.
    """
    print('fd', info[FD], 'disconnected.')
    if info[WRAPPED].dataq:
        print('  Outstanding writes:', sum(map(len, info[WRAPPED].dataq)))
    if reason:
        print(' ', reason)
    info[OBJ].close()


class Poller(object):
    """Poll resources and handle io.

    Readers are assumed to have no data available until polled
    otherwise.  Writers are assumed to be writable until polled
    otherwise.
    """
    def __init__(self, wrap, handle_end=default_handler):
        """Initialize a poller.

        wrap: func(poller, resource).
            Wrapper function to wrap resources.
            Result should have these methods:
                readloop(): generator, each step reads some data
                writeloop(): generator, each step writes some data
                write(data): Queue data to write.
        handle_end: callable
            If None, do nothing.
            Otherwise call handle_end(poller, wrapped)
        """
        self.resources = {}
        self.rpending = {}
        self.wpending = {}
        self.statechanged = set()
        self.out = []
        self._wrap = wrap
        self.handle_end = handle_end

        self.running = False
        self.tasks = []
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)

        # Regarding control, polling is generally a blocking operation.
        # Adding a separate pollable object allows unblocking polling
        # to perform some action like adding/removing polled resources.
        # if there are a large number of tasks, it might block.
        # as a result, writing should be done without lock.
        self.control = rwpair.RWPair()
        fd = self.control.fileno()
        self.resources[fd] = [
            fd, self.control,
            self.readloop(), None,
            self, True, None]
        self.rpoll(fd)

    # ------------------------------
    # public interface
    # ------------------------------
    def get(self, timeout=None):
        """Get read results.

        timeout: None|float, amount of time to wait for data. None
                 means wait until next data.
        """
        with self.cond:
            ret = self.out
            if ret:
                self.out = []
                return ret
            elif wait_for(self.cond, self.ready, timeout):
                # other thread may have swapped out self.out so
                # get attr again.
                ret = self.out
                self.out = []
                return ret

    def register(self, resource, read=True, write=True):
        """Add an item to poller threadsafe.

        resource: should have fileno(), readinto(), and write() methods.
        read: bool, mark for read polling.
        write: bool, mark for write polling.

        If there is an error in reading/writing for all marked functionalities,
        the resource will be removed and the handler will be called.

        Return a wrapped object.  Writing should use that object.
        """
        wrapped = self.wrap(resource)
        if read:
            wrapped[RPOLL] = True
        else:
            wrapped[RPOLL] = None
        if write:
            wrapped[WPOLL] = False
        else:
            wrapped[WPOLL] = None
        with self.lock:
            self.tasks.append((self.add, wrapped))
        self.control.write(b' ')
        return wrapped[WRAPPED]

    def unregister(self, resource):
        """Remove an item from poller threadsafe."""
        if not isinstance(resource, int):
            resource = resource.fileno()
        with self.lock:
            self.tasks.append((self.remove, resource))
        self.control.write(b' ')

    def __del__(self):
        self.close()

    def close(self):
        self.stop()
        for item in list(self.resources):
            self.remove(item)
        self.control.close()

    def step(self):
        """Poll registered resources and handle a little bit.

        Use this for custom polling loop.
        """
        for item in self.rpending.values():
            next(item)
        for item in self.wpending.values():
            next(item)
        if self.statechanged:
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
                    self.nopoll(fd)
                    if info[RPOLL] is None and info[WPOLL] is None:
                        self.remove(fd)
                        try:
                            self.handle_end(self, info)
                        except Exception:
                            traceback.print_exc()
            self.statechanged.clear()

    def run(self):
        """Run polling loop in current thread."""
        self.running = True
        while self.running:
            self.step()

    def start(self):
        """Start polling loop in a separate thread."""
        if getattr(self, 'thread', None) is None:
            self.thread = threading.Thread(target=self.run)
            self.thread.start()

    def stop(self):
        """Stop polling thread."""
        if getattr(self, 'thread', None) is not None:
            with self.lock:
                self.tasks.append(None)
            self.control.write(b'0')
            self.thread.join()
            del self.thread

    def write_items(self, fd, dataq, write):
        """Generator to write items in dataq.

        When dataq is empty, then stop processing and wait until next()
        call.  Start polling if would block.
        """
        while 1:
            if dataq:
                item = dataq.popleft()
                target = len(item)
                written = 0
                while 1:
                    try:
                        amt = write(target)
                    except OSError as e:
                        if e.errno in (EWOULDBLOCK, EAGAIN):
                            poller.statechanged.add(fd)
                            poller.resources[fd][WPOLL] = True
                            yield
                        elif e.errno == EINTR:
                            continue
                        else:
                            self.statechanged.add(fd)
                            poller.resources[fd][WPOLL] = None
                            yield -1
                            return
                    except Exception:
                        traceback.print_exc()
                        self.statechanged.add(fd)
                        poller.resources[fd][WPOLL] = None
                        yield -1
                        return
                    else:
                        yield
                        written += amt
                        if written < target:
                            item = item[amt:]
                        else:
                            break
            else:
                self.statechanged.add(fd)
                yield

    def read_error(self, fd):
        self.resources[fd][RPOLL] = None
        self.statechanged.add(fd)

    def fill_buf(self, fd, readinto, buf, target):
        """A generator to read until buf is full.

        The last yield is the total size read.

        fd: the fd of the resource.
        readinto: readinto function
        buf: a memoryview of buffer to fill
        target: target bytes to read, should be <= len(buf)

        Handle the appropriate resource manipulations.
        1. If EOF is encountered, remove from rpending.
        2. If EAGAIN/EWOULDBLOCK, remove from rpending and
           begin read polling.
        3. Otherwise, no state change, last yield is the total number
           of bytes read.
        """
        total = 0
        while 1:
            try:
                amt = readinto(buf)
            except OSError as e:
                if e.errno in (EWOULDBLOCK, EAGAIN):
                    self.statechanged.add(fd)
                    self.resources[fd][RPOLL] = True
                    yield
                elif e.errno == EINTR:
                    continue
                else:
                    traceback.print_exc()
                    self.statechanged.add(fd)
                    self.resources[fd][RPOLL] = None
                    yield -1
                    return
            except Exception:
                traceback.print_exc()
                self.statechanged.add(fd)
                self.resources[fd][RPOLL] = None
                yield -1
                return
            else:
                if amt:
                    total += amt
                    if total >= target:
                        yield total
                        return
                    v = v[amt:]
                    yield 0
                else:
                    self.statechanged.add(fd)
                    if amt is None:
                        self.resources[fd][RPOLL] = True
                        yield
                    else:
                        self.resources[fd][RPOLL] = None
                        yield -1
                        return

    def enqueue_write(self, args):
        """Enqueue a write.

        args: fd, q, func, data
            fd: int, fileno of resource
            q: dataq to check length
            func: function for adding data.
            data: data to add
        """
        fd, q, func, data = args
        if not q:
            info = self.resources[fd]
            if info[WPOLL] is False:
                self.wpending[fd] = info[WGEN]
        func(data)


    # ------------------------------
    # internal interface
    # ------------------------------
    def readgen(self, fd):
        """Generator to read chunks of data.

        processor: generator, step to process some data.
        send() is used to send the amount of data read.
        It should yield buffer to read into and target length
        """
        _, obj, _, _, wrapped, _, _ = self.resources[fd]
        processor = wrapped.process_loop()
        readinto = obj.readinto
        buf, total, target = next(processor)
        while 1:
            while total < target:
                try:
                    amt = readinto(buf[total:])
                except Exception as e:
                    if isinstance(e, OSError):
                        if e.errno in (EWOULDBLOCK, EAGAIN):
                            self.statechanged.add(fd)
                            self.resources[fd][RPOLL] = True
                            yield
                            continue
                        elif e.errno == EINTR:
                            continue
                    traceback.print_exc()
                    self.statechanged.add(fd)
                    self.resources[fd][RPOLL] = None
                    yield -1
                    return
                else:
                    if amt:
                        total += amt
                    else:
                        self.statechanged.add(fd)
                        if amt is None:
                            self.resources[fd][RPOLL] = True
                            yield
                        else:
                            self.resources[fd][RPOLL] = None
                            yield -1
                            return
            buf, total, target = processor.send(total)

    def readloop(self):
        """Handle tasks."""
        lck = self.lock
        while 1:
            with lck:
                tasks = self.tasks
                self.control.read(len(tasks))
                self.tasks = []
            for task in tasks:
                try:
                    task[0](task[1])
                except TypeError:
                    if task is None:
                        self.running = False
                        break
                    traceback.print_exc()
                except Exception:
                    traceback.print_exc()
            wrapped = self.resources[self.control.fileno()]
            wrapped[RPOLL] = True
            if wrapped[WPOLL]:
                self.rwpoll(wrapped[0])
            else:
                self.rpoll(wrapped[0])
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

    def wrap(self, resource):
        """Wrap a resource.

        Return [
            0: fileno: int, the file number.
            1: resource: the object.
            2: rgenerator: generator, next() should read and process a bit.
            3: wgenerator: generator, next() should write a bit.
            4: writer wrapper
            5: rpolling: bool|None,
                True: should be polled.
                False: not polled (being handled)
                None: read error, not handled or polled
            6: wpolling: bool|None, whether object should be write polled.
                True: should be polled.
                False: not polled (being handled or no data to handle)
                None: read error, not handled or polled
        ]
        """
        fd = resource.fileno()
        wrapped = self._wrap(self, resource)
        wgen = getattr(wrapped, 'writeloop', None)
        if wgen is not None:
            wgen = wgen()
        return [
            fd, resource,
            wrapped.readloop(), wgen,
            wrapped, True, False]

    def add(self, wrapped):
        """Add a wrapped resource in polling thread.

        wrapped: wrapped non-blocking file-like object.
        """
        fd = wrapped[FD]
        orig = self.resources.pop(fd, None)
        if orig is not None:
            self.remove(fd)
            self.handle_end(self, orig)
        self.resources[fd] = wrapped
        if wrapped[RPOLL]:
            self.rpoll(fd)

    def remove(self, fd):
        """Unregister from poller in polling thread.

        This should be called from same thread as the polling thread.
        """
        self.rpending.pop(fd, None)
        self.wpending.pop(fd, None)
        self.resources.pop(fd, None)

    def ready(self):
        return bool(self.out)


class Poller2(Poller):
    """Poll resources and handle io.

    readloop should yield (view, target size) tuple.
    each poll step will read a little and .send() the net size
    This alternative implementation has fewer generators so maybe
    perform better? but have to save state, so maybe not? just
    testing alternative implementation

    """
    def __iter__(self):
        lck = self.lock
        buf = memoryview(bytearray(io.DEFAULT_BUFFER_SIZE))
        while 1:
            size = yield buf, 1
