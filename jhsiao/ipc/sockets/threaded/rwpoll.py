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
from __future__ import print_function
import sys
import os
import uuid

from . import sockfile
from ..formats import bases

class RWPair(object):
    """Read/Write pollable/selectable fd pair.

    Use sockets if windows, else os.pipe()
    """
    def __init__(self, sock=None):
        """Initialize.

        sock: a listening socket if provided.
            The sock will be connected to to create an in/out socket pair
            comopatible with select.select that can be used to interrupt
            any polling.
        """
        if sock is None:
            try:
                L = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            except AttributeError:
                L = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    L.bind(('127.0.0.1', 0))
                    L.listen(1)
                    self.r, self.w = self._from_listener(L)
                finally:
                    L.close()
            else:
                try:
                    L.bind('\0' + uuid.uuid4().hex)
                    L.listen(1)
                    self.r, self.w = self._from_listener(L)
                finally:
                    L.close()
        else:
            self.r, self.w = self._from_listener(sock)
        self.fileno = self.r.fileno

    def _from_listener(self, L):
        c = socket.socket(L.family, L.type)
        c.settimeout(0)
        try:
            c.connect(L.getsockname())
        except Exception:
            c.close()
            raise
        else:
            s, a = L.accept()
            s.settimeout(0)
            return (sockfile.Sockfile(s), sockfile.Sockfile(c))

    def clear(self):
        """Consume a byte."""
        try:
            self.r.read(1)
        except EnvironmentError as e:
            if e.errno not in bases.WOULDBLOCK:
                raise

    def set(self):
        """Send a byte to make polling return readable."""
        try:
            self.w.send(b'1')
        except EnvironmentError as e:
            if e.errno not in bases.WOULDBLOCK:
                raise

    def fileno(self):
        return self.fileno()

    def close(self):
        self.inp.close()
        self.out.close()


class PollRegister(RWPair):
    def __init__(self, poller, sock=None):
        super(PollRegister, self).__init__(sock)
        self.q = []

    def register(self, *args):
        self.q.append(args)

    def readinto1(self, out):
        with self.lock:
            q = self.q
            self.q = []
        for args in q:
            self.clear()
            poller.register(*args)
        return -2



class _Poller(object):
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

class _RPoller(_Poller):
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

class _WPoller(_Poller):
    """Write polling object."""
    def register(self, item, mode):
        """Mode will be ignored, only write polling supported."""
        raise NotImplementedError

    def poll(self, out, w):
        """Poll objects and flush1() on writers.

        No timeout if w is empty else 0.
        Return updated list of items that have data to write and can
        write.
        """
        raise NotImplementedError

class _RWPoller(_Poller):
    """Combine read and write polling."""
    def poll(self, out, r, w):
        """Poll objects for read and write.

        Combine behavior of _RPoller and _WPoller.
        Return updated readers and writers lists.
        """
        pass

if hasattr(select, 'select'):
    __all__.append('RSelectPoller')
    __all__.append('WSelectPoller')
    __all__.append('RWSelectPoller')

    class RSelectPoller(_RPoller):
        def __init__(self, verbose=False):
            self.r = set()
            self.verbose = verbose
            self.unregister = self.r.discard

        def register(self, item, mode):
            self.r.add(item)

        def poll(self, out, r):
            extra = select.select(self.r, (), (), 0 if r else None)[0]
            if extra:
                self.r.difference_update(extra)
                r.extend(extra)
            kp = []
            for item in r:
                result = item.readinto1(out)
                if result is None or result == -2:
                    self.r.add(item)
                elif result == -1:
                    fd = item.fileno()
                    try:
                        item.close()
                    except Exception as e:
                        if self.verbose:
                            print(
                                '{} errored: {}'.format(fd, e),
                                file=sys.stderr)
                    else:
                        if self.verbose:
                            print(
                                '{} Disconnected'.format(fd),
                                file=sys.stderr)
                else:
                    kp.append(item)
            return kp

    class WSelectPoller(_SPoller):
        """Use select to poll for writes."""
        # On Windows, if a socket is closed mid-select() for write,
        # select will unblock, but return no items at all.  The bad fd
        # must be searched for via iteration.
        # A closed fd will be polled as available for read, but
        # available for read doesn't necessarily mean that the socket
        # was closed.
        def __init__(self, interrupt, verbose=False):
            self.r = set()
            self.w = set()
            self.verbose = verbose

        def unregister(self, item):
            self.r.discard(item)
            self.w.discard(item)

        def register(self, item, mode):
            """Register item.

            If mode == 'r', assume it is an item being registered to
            interrupt polling so write-polling items can be registered.
            """
            if 'r' in mode:
                self.r.add(item)
            else:
                self.r.discard(item)
            if 'w' in mode:
                self.w.add(item)
            else:
                self.w.discard(item)

        def poll(self, out, w):
            r, extra, _ = select.select(
                self.r, self.w, (), 0 if w else None)
            if extra:
                self.w.difference_update(extra)
                w.extend(extra)
            if r:
                self.w.difference_update(r)
                for item in r:
                    if item is self.interrupt:
                        item.read(1)
                        self.r.add(item)
                    else:
                        self.r.discard(item)
                        item.close()
            kp = []
            for item in w:
                result = item.flush1(out)
                if result is None:
                    self.w.add(item)
                elif result < 0:
                    fd = item.fileno()
                    try:
                        item.close()
                    except Exception as e:
                        if self.verbose:
                            print(
                                '{} errored: {}'.format(fd, e),
                                file=sys.stderr)
                    else:
                        if self.verbose:
                            print(
                                '{} Disconnected'.format(fd),
                                file=sys.stderr)
                else:
                    if item:
                        kp.append(item)
            return kp
