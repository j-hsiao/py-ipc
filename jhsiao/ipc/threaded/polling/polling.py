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
__all__ = ['Poller', 'RPoller', 'WPoller', 'RWPoller']


import sys
import threading

from . import rwpair

if sys.version_info > (3,4) and isinstance(threading.Condition, type):
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
        self._cond = threading.Condition()
        self._running = True
        self._thread = None
        self._rwpair = rwpair.RWPair()
        self.fileno = self._rwpair.fileno
        self[self] = self.s
        self.bad = []

    def fileno(self):
        return self.fileno()

    def readinto1(self, out):
        """Handle any interrupts of the polling."""
        raise NotImplementedError

    def __iter__(self):
        """Iterate on registered items."""
        raise NotImplementedError

    def step(self):
        """Poll once and incremental read/write.

        Return True if good to continue
        """
        raise NotImplementedError

    def start(self):
        """Start a polling thread."""
        with self._cond:
            if self._thread is not None:
                return
            self._thread = threading.Thread(target=self._run)
            self._running = True
            self._thread.start()

    def stop(self):
        """Stop a polling thread."""
        with self._cond:
            if not self._running:
                return
            self._running = False
            self._rwpair.write(b'1')
            thread = self._thread
        thread.join()

    def _run(self):
        try:
            while self.step():
                pass
        finally:
            with self._cond:
                self._running = False
                self._thread = None

    def unregister(self, item):
        """Unregister an item. public use."""
        raise NotImplementedError

    def register(self, item, mode):
        """Register item under mode.

        Re-register to change mode.
        public use
        """
        raise NotImplementedError

    def __delitem__(self, item):
        """Unregister in loop."""
        raise NotImplementedError
    def __setitem__(self, item, mode):
        """Register in loop."""
        raise NotImplementedError

    def close(self):
        """Close the poller.

        Any registered items are left alone.
        """
        self.stop()
        self._rwpair.close()

class RPoller(object):
    """Poller with reading functionality."""
    def __init__(self):
        super(RPoller, self).__init__()
        self.received = []

    def _pred(self):
        """predicate for condition variable.

        Note that using self.received.__len__ is not enough because
        another thread may have swapped out received.  This is necessary
        to be threadsafe and not double up in case get is called
        from multiple threads.
        """
        return self.received

    def get(self, timeout=None):
        """Get list of available data."""
        with self._cond:
            if self.received or _wait_cond(self._cond, self._pred, timeout):
                ret = self.received
                self.received = []
                return ret
            return ()

class WPoller(Poller):
    """Write polling object."""
    def __init__(self):
        super(WPoller, self).__init__()

    def write(self, fobj, data):
        """Enqueue a write on fobj with data."""
        raise NotImplementedError

class RWPoller(WPoller, RPoller):
    """Combine read and write polling."""
    def __init__(self):
        super(RWPoller, self).__init__()
