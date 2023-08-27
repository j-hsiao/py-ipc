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
"""
__all__ = ['Poller', 'RPoller', 'WPoller', 'RWPoller']

class Poller(object):
    """Register and poll objects.

    Polling will generally be either without timeout, or nonblocking.
    As a result, adding new items to poll must interrupt any current
    poll.  This will generally be done by some item that has been
    registered for read polling.
    """
    def unregister(self, item):
        raise NotImplementedError
    def register(self, item, mode):
        raise NotImplementedError
    def close(self):
        pass

class RPoller(Poller):
    """Read polling object."""
    def register(self, item, mode):
        """Mode will be ignored, only read polling supported."""
        raise NotImplementedError

    def poll(self, out, r):
        """Poll objects and readinto1() on readers.

        No timeout if r is empty else 0.
        Return list of updated readers.
        Any messages that were parsed will be added to out.
        """
        raise NotImplementedError

class WPoller(Poller):
    """Write polling object."""
    def register(self, item, mode):
        """Mode will be ignored, only write polling supported.

        All items registered with read are assumed to return -2 on
        readinto1() and the input argument should be unused.
        """
        raise NotImplementedError

    def poll(self, out, w):
        """Poll objects and flush1() on writers.

        No timeout if w is empty else 0.
        Return updated list of items that have data to write and can
        write.
        """
        raise NotImplementedError

class RWPoller(Poller):
    """Combine read and write polling."""
    def poll(self, out, r, w):
        """Poll objects for read and write.

        Combine behavior of RPoller and WPoller.
        Return updated readers and writers lists.
        """
        pass
