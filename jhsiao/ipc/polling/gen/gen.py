"""Generator interfaces."""
import collections

try:
    import errno
except ImportError:
    errno = None

EAGAIN = getattr(errno, 'EAGAIN', 11)
EWOULDBLOCK = getattr(errno, 'EWOULDBLOCK', 10035)
EINTR = getattr(errno, 'EINTR', 4)

def writeall(write, data):
    """Generator to Write all bytes in data.

    write: the write function.
    data:  the data to write

    Return the total number of bytes written.
    Assuming write polling,
        0: no data written, broken resource.
        -1: error
        N: the amount of data written.
    The last yield is the total data written.
    """
    target = len(data)
    total = 0
    v = memoryview(data)
    while total < target:
        try:
            amt = write(v)
        except OSError as e:
            if e.errno in (EAGAIN, EWOULDBLOCK):
                yield total
                return
            elif e.errno == EINTR:
                continue
        else:
            if amt:
                total += amt
                v = v[amt:]
                yield amt
            else:
                yield total
                return
    yield total


class Gen(object):
    def __init__(self, poller, f):
        self.poller = poller
        self.f = f
        self.dataq = collections.deque()

    def write(self, data):
        with self.poller.lock:
            self.poller.tasks.append(
                (self.poller.enqueue_write, self.f.fileno(), data))
        self.poller.control.write(b' ')

    def readloop(self):
        raise NotImplementedError

    def writeloop(self):
        return self.poller.write_items(
            self.f.fileno(), self.dataq, self.f.write)
