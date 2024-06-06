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
        super(SelectPollerMixIn, self).__init__(*args, **kwargs)
        self._rpoll = set()
        self._wpoll = set()

    def rpoll(self, fd):
        """(re)Register for read-only polling."""
        self._rpoll.add(fd)
        self._wpoll.discard(fd)

    def wpoll(self, fd):
        """(re)Register for write-only polling."""
        self._rpoll.discard(fd)
        self._wpoll.add(fd)

    def rwpoll(self, fd):
        """(re)Register for read and write polling."""
        self._rpoll.add(fd)
        self._wpoll.add(fd)

    def nopoll(self, fd):
        """(re)Register for no polling."""
        self._rpoll.discard(fd)
        self._wpoll.discard(fd)

    def step(self):
        if self.rpending or self.wpending:
            r, w, x = select.select(self._rpoll, self._wpoll, (), 0)
        else:
            r, w, x = select.select(self._rpoll, self._wpoll, ())
        for fd in r:
            wrapped = self.resources[fd]
            wrapped[RPOLL] = False
            self.rpending[fd] = wrapped[RGEN]
            self._rpoll.discard(fd)
        for fd in w:
            wrapped = self.resources[fd]
            wrapped[WPOLL] = False
            self.wpending[fd] = wrapped[WGEN]
            self._wpoll.discard(fd)
        super(SelectPollerMixIn, self).step()

class SelectPoller(SelectPollerMixIn, poller.Poller):
    pass
