"""Generic optimized polling for handling formats classes.

These pollers all operate like one-shot

considerations:
readonly or writeonly polling is easy.

Consider read and write in same loop.  Suppose polled read.  If oneshot,
then can no longer poll write even if wanted to.  must check.  Then if
want to re-arm read, must check write too or might lose write polling if
it was requested before.  As a result, no read/write in same loop, use 2
separate threads instead.
"""
from __future__ import print_function
import sys

class _Poller(object):
    """Register and poll objects.

    Objects should conform to
    jhsiao.ipc.sockets.formats.bases.Reader/Writer
    """
    def unregister(self, item):
        raise NotImplementedError
    def register(self, item):
        raise NotImplementedError
    def close(self):
        pass

class _RPoller(_Poller):
    """Read polling object.

    If there are new items to poll reading, they probably
    come from some kind of listening socket.  You can use
    the classes in .listener or some separate interrupting
    file with a corresponding readinto1 if necessary.
    """
    def poll(self, out, r):
        """Poll objects and readinto1() on readers.

        Assume registered objects are only r
        No timeout if r is empty else 0.

        Return list of new readers.
        """
        raise NotImplementedError

class _WPoller(_Poller):
    """Write polling object.

    For writers, polling needs are probably decided by a separate thread
    which means the poll needs to be interruptible so that new objects
    can be polled as well.
    """
    def __init__(self, interrupt, verbose=False):
        self.verbose = verbose
        self.interrupt = interrupt

    def poll(self, out, w):
        """Poll objects and flush1() on readers.

        Assume registered objects are only r
        No timeout if w is empty else 0.
        Return list of new writers.
        """
        raise NotImplementedError

if hasattr(select, 'select'):
    __all__.append('RSelectPoller')
    __all__.append('WSelectPoller')
    class RSelectPoller(_RPoller):
        def __init__(self, verbose=False):
            self.r = set()
            self.verbose = verbose
        def register(self, item):
            self.r.add(item)
        def unregister(self, item):
            self.r.discard(item)
        def poll(self, out, r):
            extra = select.select(self.r, (), (), 0 if r else None)[0]
            if extra:
                self.r.difference_update(extra)
                r.extend(extra)
            kp = []
            for item in r:
                result = item.readinto1(out)
                if result is None:
                    self.r.add(item)
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
                    kp.append(item)
            return kp

    class WSelectPoller(_SPoller):
        def __init__(self, interrupt, verbose=False):
            # polling for write, but if socket closes select will
            # unblock but the item will not be returned in any list
            # unless it is also polling reads.  The error list is
            # empty as well.
            self.w = set()
            self.r = set([interrupt])
            self.verbose = verbose
            self.interrupt = interrupt

        def register(self, item):
            self.w.add(item)
        def unregister(self, item):
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
