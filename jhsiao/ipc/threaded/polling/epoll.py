# The bits returned in revents can include any of those specified in
# events, or one of the values POLLERR, POLLHUP, or POLLNVAL.  (These
# three bits are meaningless in the events field, and will be set in the
# revents field whenever the corresponding condition is true.)
#
# observations:
# poll performance is proportional to the number of events.  If data is
# large or constant, then fds will be constantly polled.  EPOLLET
# reduces number of polled events assuming that sockets are ready until
# EAGAIN/EWOULDBLOCK.
#
# 1. when event is fired all events are fired
#    ie: data to read, write blocked
#           poll->EPOLLIN
#           poll->nothing
#        remote reads
#           poll->EPOLLIN|EPOLLOUT
# 2. modify results in all events being fired again.
#
# ex. if get read->modify to remove read from mask
# but then ET doesn't really do anything...
# track whether reading or writing individually and ignore redundant?
#
# TODO considerations:
# 1. suppose polling gives HUP/ERR/NVAL, want to unregister it from
# poller (otherwise it'll keep getting polled)
# BUT. if it was already being processed in r/w?
# if w: would write->error?
# if r: would read->error?
# maybe no extra processing needed
# would unregister but already checked if need to unregister from poller
# so safe
#
# thought: handling hup/err/nval separately might not be necessary
# since trying to read/write if it was in error state should result
# in error and removing it/adding to bad anyways.
#
# for writer, get item into w somehow
# and also register somehow?
#
# but if register via read signal, can it be guaranteed to be
# registered before the write is handled?: add to w and register via the
# read signal, means w is never unregistered
__all__ = ['EpollPoller']
import select

from . import genpolling
from jhsiao.ipc import errnos

class EpollPoller(genpolling.GenPoller):
    r = select.EPOLLIN | select.EPOLLET
    w = select.EPOLLOUT | select.EPOLLET
    rw = r | w
    s = select.EPOLLIN
    ro = select.EPOLLIN
    wo = self.EPOLLOUT
    cls = select.epoll

    def _new_item(item, mode):
        return [item, False, int(bool(mode & self.wo))]

    def _update_mode(self, L, m):
        pass

    def _poll(self, items, reading, writing, timeout):
        for fd, md in self._poller.poll(timeout):
            L = items[fd]
            if not L[1] and md & self.ro:
                L[1] = True
                reading.append(L[0])
            if not L[2] and md & self.wo:
                if L[0]:
                    L[2] = 2
                    writing.append(L[0])
                else:
                    L[2] = 1
