from __future__ import print_function
__all__ = [
    'RSelectPoller',
    'WSelectPoller',
    'RWSelectPoller',
]
import select
import sys

from . import polling

class RSelectPoller(polling.RPoller):
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

class WSelectPoller(polling.WPoller):
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
            for item in r:
                r.readinto1(None)
        if extra:
            self.w.difference_update(extra)
            for item in extra:
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
