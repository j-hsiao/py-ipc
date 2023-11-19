# The bits returned in revents can include any of those specified in
# events, or one of the values POLLERR, POLLHUP, or POLLNVAL.  (These
# three bits are meaningless in the events field, and will be set in the
# revents field whenever the corresponding condition is true.)
#
# Considerations:
# registering fds
#   1. polling handled in a separate thread
#   2. items are registered via a read signal
#         (writing to some fd to interrupt poll)
#   3. For read:
#         register once, and continue polling
#   4. For write:
#         If initial write is in main thread:
#             race condition: maybe something is being written then?
#         The register fd can try writing and only then add to w if not
#             fully written.  No race conditions.
# handling HUP/ERR/NVAL
#   1. suppose polling gives HUP/ERR/NVAL, want to unregister it from
#   poller (otherwise it'll keep getting polled)
#   BUT. if currently in r or w, would error, can just fully unregister
#   without removing from r or w
#   2. yet also, maybe don't need explicit handling? read/write would
#       indicate an error anyways...
#
# bad, closing:
#   if closed, fileno() may error, but unregister calls fileno()?
#   how to handle
#
# same thing may be added to bad multiple times...
# maybe use a set? or doesn't matter?
__all__ = []
import select

from . import genpolling
from jhsiao.ipc import errnos


class PPoller(genpolling.GenPoller):
    ro = r = select.POLLIN
    wo = w = select.POLLOUT
    rw = r|w
    s = r
    nr = ~r
    nw = ~w

    TIMESCALE = 1000

    def _new_item(self, item, mode):
        return [item, False, int(bool(mode & self.wo)), mode]

    def _update_mode(self, L, m):
        L[3] = m

    def _reset_mode(self, fd, L, m):
        L[3] |= m
        self._poller.modify(fd, L[3])

    def _poll(self, items, reading, writing, timeout):
        for fd, md in self._poller.poll(timeout):
            L = items[fd]
            if not L[1] and md & self.ro:
                L[1] = True
                reading.append(L[0])
                L[3] &= self.nr
            if not L[2] and md & self.wo:
                if L[0]:
                    L[2] = 2
                    writing.append(L[0])
                else:
                    L[2] = 1
                L[3] &= self.nw
            self._poller.modify(fd, L[3])


if hasattr(select, 'devpoll'):
    class DevpollPoller(PPoller):
        cls = select.devpoll
    __all__.append('DevpollPoller')
if hasattr(select, 'poll'):
    class PollPoller(PPoller):
        cls = select.poll
    __all__.append('PollPoller')
