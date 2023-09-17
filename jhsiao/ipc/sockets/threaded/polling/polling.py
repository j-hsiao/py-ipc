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
    Controller = None
    def __iter__(self):
        """Iterate on registered items."""
        raise NotImplementedError

    def __delitem__(self, item):
        """Call unregister."""
        self.unregister(item)

    def __setitem__(self, item, mode):
        """Call register."""
        self.register(item, mode)

    def unregister(self, item):
        """Unregister an item."""
        del self[item]

    def register(self, item, mode):
        """Register item under mode.

        Re-register to change mode.
        """
        self[item] = mode

    def controller(self):
        """Return a controller class for managing objects.

        The controller methods should generally be called in a main
        thread while poll/fill would be called in a separate thread.
        """
        raise NotImplementedError

    def poll(self, timeout):
        """Poll objects and return backend-specific object.

        No arg means no timeout.
        """
        raise NotImplementedError

    def close(self):
        """Close the poller.

        Any registered items are left alone.
        """
        pass

class RPoller(Poller):
    """Poll for reads.

    When registering items, read flag is always added and write flag is
    always ignored.
    """
    def __init__(self):
        self.rq = []

    def fill(self, pollout, r, out, bad):
        """Read a little data from each item.

        pollout: poll output
        r: list of readers
        out: output container
        bad: list of bad items.
        """
        raise NotImplementedError

class WPoller(Poller):
    """Write polling object."""
    def __init__(self):
        self.wq = []

    def fill(self, pollout, w, bad):
        """Call flush1() on writers.

        w will be updated with writers that have not blocked and have
        more data towrite.
        Bad items are added to bad (disconnected or error.)
        """
        raise NotImplementedError

class RWPoller(Poller):
    """Combine read and write polling."""
    def __init__(self):
        self.rq = []
        self.wq = []

    def fill(self, pollout, r, w, out, bad):
        """Like WPoller.fill() and RPoller.fill()."""
        raise NotImplementedError

class RegisterCtrl(RWPair):
    """Poller control class.

    Generally, objects will either be read from or written to, possibly
    both.  For reading, objects should probably be registered to be
    polled and left.  The corresponding readinto1 method should place
    any complete messages into a queue or list.

    For writers, write polling is only needed if writing would block.
    As a result, they shouldn't necessarily be directly registered.
    """
    def __init__(self, poller, rlist, wlist, sock=None, lock=NullLock()):
        super(PollRegister, self).__init__(sock)
        self.lock = lock
        self.poller = poller
        for attr in ('r', 'w', 'rw', 's'):
            setattr(self, attr, getattr(self.poller, attr))
        self.rlist = rlist
        self.wlist = wlist
        self.rq = []
        self.wq = []

    def write(self, *args):
        """Register writing some data.

        args: pair of Writer and data.
             Writer is a `jhsiao.ipc.formats.bases.Writer`.
             data is some data that would be given to the writer's
             write() method.
        """
        with self.lock:
            self.wq.append(args)
            self.wf.write(b'1')

    def register(self, *args):
        """Add an item to be registered to the poll.

        This should match the argument of poller.register.
        """
        with self.lock:
            self.rq.append(args)
            self.wf.write(b'1')

    def readinto1(self, out):
        """Register items."""
        with self.lock:
            rq = self.rq
            self.rq = []
            wq = self.wq
            self.wq = []
        poller = self.poller
        for args in rq:
            try:
                poller.register(*args)
            except Exception:
                traceback.print_exc()
            self.rf.read(1)
        for w, data in wq:
            w.write(data)
            result = w.flush1()
            if result == None:
                poller.modify()? register?
            elif result == -1:
                pass
            elif w:
                pass
        return -2

