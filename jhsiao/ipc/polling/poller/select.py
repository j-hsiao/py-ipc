"""Implement poller interface using select.select."""
__all__ = ['SelectPollerMixIn']
import select

from . import poller

RGEN = poller.RGEN
WGEN = poller.WGEN
RPOLL = poller.RPOLL
WPOLL = poller.WPOLL

class SelectPollerMixIn(object):
    def __init__(self, *args, **kwargs):
        self.rpolls = set()
        self.wpolls = set()
        super(SelectPollerMixIn, self).__init__(*args, **kwargs)

    def rpoll(self, fd):
        """(re)Register for read-only polling."""
        self.rpolls.add(fd)
        self.wpolls.discard(fd)

    def wpoll(self, fd):
        """(re)Register for write-only polling."""
        self.rpolls.discard(fd)
        self.wpolls.add(fd)

    def rwpoll(self, fd):
        """(re)Register for read and write polling."""
        self.rpolls.add(fd)
        self.wpolls.add(fd)

    def nopoll(self, fd):
        """(re)Register for no polling."""
        self.rpolls.discard(fd)
        self.wpolls.discard(fd)

    def step(self):
        if self.rpending or self.wpending:
            r, w, x = select.select(self.rpolls, self.wpolls, (), 0)
        else:
            r, w, x = select.select(self.rpolls, self.wpolls, ())
        for fd in r:
            wrapped = self.resources[fd]
            wrapped[RPOLL] = False
            self.rpending[fd] = wrapped[RGEN]
            self.rpolls.discard(fd)
        for fd in w:
            wrapped = self.resources[fd]
            wrapped[WPOLL] = False
            self.wpending[fd] = wrapped[WGEN]
            self.wpolls.discard(fd)
        super(SelectPollerMixIn, self).step()

class SelectPoller(SelectPollerMixIn, poller.Poller):
    pass
