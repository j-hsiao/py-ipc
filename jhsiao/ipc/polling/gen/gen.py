"""Generator interfaces."""
try:
    import errno
except ImportError:
    errno = None

EAGAIN = getattr(errno, 'EAGAIN', 11)
EWOULDBLOCK = getattr(errno, 'EWOULDBLOCK', 10035)
EINTR = getattr(errno, 'EINTR', 4)

def readall(readinto, buf):
    """Generator to until a buffer is full.

    readinto: function to read data into buf.
    buf: buffer to read into.

    Yield the size of each sequential read/write until

    Return the number of bytes read.
    Assuming read polling:
        < len(buf): EOF OR no data available (retry later)
        -1: error


    choice1:
        -1: EOF or error, stop reading, no more polling.
        0: not finished, keep reading
        X: number of bytes read.
           If < len(buf), Stop reading, go back to polling
    """
    target = len(buf)
    total = 0
    v = memoryview(buf)
    while 1:
        try:
            amt = readinto(v)
        except OSError as e:
            if e.errno in (EAGAIN, EWOULDBLOCK):
                yield total
                return
            elif e.errno == EINTR:
                continue
            else:
                yield -1
                return
        else:
            if amt:
                total += amt
                if total == target:
                    yield total
                    return
                v = v[amt:]
                yield 0
            else:
                yield -1
                return

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






class WGen(object):
    def __init__(self, poller, f):
        self.poller = poller
        self.f = f

    def write(self, data):
        """Prepare data to be written in the generator."""
        raise NotImplementedError

    def __iter__(self):
        """Write data chunk by chunk."""
        raise NotImplementedError
