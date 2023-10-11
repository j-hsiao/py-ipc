"""Poll objects and handle incremental read/writes for streams.

Handling should follow the classes in `jhsiao.ipc.formats` depending
on whether the object is readable or writeable or both.


Registered readable objects must support:
    readinto1(out)
        Read some data and put any fully parsed data into out.  This is
        jhsiao.ipc.formats.bases.Reader.readinto1 except with an
        additional possible return value of -2.  -2 indicates that the
        item has special handling and is not registered to have one-shot
        like behavior.  Otherwise, None indicates blocking, so rearm the
        fd, -1 indicates behavior, so close() the item and discard it.
        >= 0 indicates successful reading of some data but there may be
        more so continue call readinto1() again.
    close()
        Close the item.
    fileno()
        Return the item's fileno.

Registered writable objects must support:
    flush1()
        Flush some data.  Return the amount of data flushed.
        None if would block  (start polling).
    __bool__()
        Tell whether there is more data to flush.

NOTE: before items are closed, they should be unregistered from any pollers.
Pollers do not check for invalid filenos.
"""
__all__ = ['Poller']

import sys
import threading

from . import rwpair

if (isinstance(threading.Condition, type)
        and hasattr(threading.Condition, 'wait_for')):
    _wait_cond = threading.Condition.wait_for
else:
    from jhsiao.ipc import errnos
    import time
    def _wait_cond(cond, pred, timeout=None):
        """Wait for received messages.

        Assume cond is held before this is called.
        """
        result = pred()
        if result or timeout == 0:
            return result
        elif timeout is None:
            try:
                while not pred():
                    cond.wait(None)
            except EnvironmentError as e:
                if e.errno != errnos.EINTR:
                    raise
                return _wait_cond(cond, pred, None)
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
                        if e.errno != errnos.EINTR:
                            raise
                else:
                    return False
            return True

class Poller(object):
    """Register and poll objects.

    Polling will generally be either without timeout, or nonblocking.
    As a result, adding new items to poll must interrupt any current
    poll.  This will generally be done by some item that has been
    registered for read polling.

    Poller subclasses should define attributes:
        r: register for read polling
        w: register for write polling
        rw: register for read and write polling
        s: register for special control
            (readinto1() should return -2)
            readinto1() returning -2 implies the object was registered
            with s.
    """
    def __init__(self):
        cls = getattr(self, 'cls', None)
        if cls is not None:
            self.poller = cls()
        self._cond = threading.Condition()
        self._running = True
        self._thread = None
        self._rwpair = rwpair.RWPair(buffered=True)
        self.fileno = self._rwpair.fileno
        self._data = []
        self._bad = []
        self._reading = []
        self._writing = []
        self._regq = []
        self._flushq = []

    def register(self, *args):
        """Threadsafe register an item.

        It will take effect the next call to step() or the next
        iteration in the loop if start() was called.

        args: item, mode
            item: an item with fileno().
            mode: self.[r|w|rw|s]
        """
        with self._cond:
            self._regq.append(args)
        self._rwpair.write(b'1')
        self._rwpair.flush()

    def unregister(self, item):
        """Threadsafe unregister an item.

        It will take effect the next call to step() or the next
        iteration in the loop if start() was called.

        args: item, mode
            item: an item with fileno().
            mode: self.[r|w|rw|s]
        """
        with self._cond:
            self._regq.append((item, None))
        self._rwpair.write(b'1')
        self._rwpair.flush()

    def flush(self, obj):
        """Register object for flushing until fully flushed or error."""
        with self._cond:
            self._flushq.append(obj)
        self._rwpair.write(b'1')
        self._rwpair.flush()

    def readinto1(self, out):
        """For internal use.

        Complete register/unregister/flush operations.
        """
        with self._cond:
            q = self._regq
            flush = self._flushq
            self._regq = []
            self._flushq = []
        self._rwpair.readinto(bytearray(len(q) + len(flush)))
        for item, mode in q:
            if mode is None:
                del self[item]
            else:
                self[item] = mode
        self._writing.extend(flush)

    def __call__(self):
        """For internal use.

        Return whether any data or bad objects to handle.
        """
        return self._data or self._bad

    def get(self, timeout=None):
        """Return a list of received data.

        Inputs
        ======
        timeout: float | None
            The timeout to wait for objects.
        Outputs
        =======
        result: list of 2-tuple
            Each tuple is (data, object).  data is the data that was
            received.  If it is None
        """
        with self._cond:
            if self._data or self._bad or _wait_cond(
                    self._cond, self, timeout):
                data = self._data
                bad = self._bad
                self._data = []
                self._bad = []
                return data, bad
        return (), ()

    def fileno(self):
        return self.fileno()

    def start(self):
        """Start a polling thread."""
        with self._cond:
            if self._thread is not None:
                return
            self._thread = threading.Thread(target=self._run)
            self._running = True
            self._thread.start()

    def close(self):
        """Close the poller."""
        with self._cond:
            if not self._running and self._thread is None:
                return
            self._running = False
            self._rwpair.write(b'1')
            self._rwpair.flush()
            thread = self._thread
            self._thread = None
        if thread is not None:
            thread.join()
        del self[self]
        self._rwpair.close()

    def _run(self):
        while self.step(None):
            pass

    def __iter__(self):
        """Iterate on registered items."""
        raise NotImplementedError

    def step(self, timeout=0):
        """Poll once and incremental read/write.

        Return True if good to continue.
        This can be used for manual looping.
        """
        raise NotImplementedError

    def __delitem__(self, item):
        """Directly unregister an item.  Thread unsafe."""
        raise NotImplementedError
    def __setitem__(self, item, mode):
        """Directly register an item.  Thread unsafe."""
        raise NotImplementedError
