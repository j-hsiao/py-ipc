"""Generic optimized polling for partial read/writes.

The pollers poll corresponding read/write and read/write with single
calls until blocking at which point polling is continued.  Registered
items should be in non-blocking mode or at least somehow guarantee
no blocking.

Registered readable objects must support:
    readinto1(out)
        Read some data and put any fully parsed data into out.  This is
        jhsiao.ipc.sockets.formats.bases.Reader.readinto1 except with an
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
    def fill(self, pollout, w, bad):
        """Call flush1() on writers.

        w will be updated with writers that have not blocked and have
        more data towrite.
        Bad items are added to bad (disconnected or error.)
        """
        raise NotImplementedError

class RWPoller(Poller):
    """Combine read and write polling."""
    def fill(self, pollout, r, w, out, bad):
        """Like WPoller.fill() and RPoller.fill()."""
        raise NotImplementedError
