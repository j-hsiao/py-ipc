"""Basic classes.

These classes are more oriented towards
sending/receiving entire objects.

Readers and QWriters are compatible with non-blocking io.
BWriter requires io.BufferedIOBase type behavior.
(Even non-conformant io.RawIOBase that throw instead of returning None.)
It is expected that non-conformant exception is an EnvironmentError
"""
__all__ = [
    'FileWrapper',
    'Reader',
    'BufferedReader',
    'Writer',
    'QWriter',
]

import collections
import io

from jhsiao.ipc import errnos

class FileWrapper(object):
    def __init__(self, f):
        self.f = f

    def __enter__(self):
        return self
    def __exit__(self, tp, exc, tb):
        self.close()

    def __del__(self):
        self.close()

    def fileno(self):
        return self.f.fileno()

    def detach(self):
        """Unwrap the file and return it.

        This instance should no longer be used.
        """
        ret = self.f
        self.f = None
        return ret

    def close(self):
        """Close the underlying file."""
        if self.f is not None:
            self.detach().close()

class Reader(FileWrapper):
    """Read objects.

    Readers differ from typical file-like objects in that they deal
    with sequence of objects rather than sequence of bytes/chars.
    """

    def readinto1(self, out):
        """Read some data (max 1 syscall) and append to out.

        This is useful for allowing a single thread to handle reading
        from multiple readers.

        Input
        =====
        out: container
            out should have an `append()` method.

        Output
        ======
        read: int
            The number of bytes processed into objects.
            -1 implies end of file or error.  The file should be closed.
            0 implies partial read but file still good.
            None implies would block.
        """
        raise NotImplementedError

    def readinto(self, out):
        """Call readinto1 until at least 1 object.

        It is possible that no objects were added:
        If no more data or error, return -1.
        If would block, return None
        """
        result = self.readinto1(out)
        try:
            while result == 0:
                result = self.readinto1(out)
        except EnvironmentError as e:
            if e.errno in errnos.WOULDBLOCK:
                return None
            elif e.errno != errnos.EINTR:
                raise
            else:
                return self.readinto(out)
        return result

    def read(self):
        """Same as readinto(), but return a new list.

        Also return the readinto count because no other way
        to tell whether partial read or eof.
        """
        L = []
        return L, self.readinto(L)

class BufferedReader(Reader):
    """Read into a buffer that may grow.

    BufferedReader will try to use readinto1 if available to avoid
    double buffering.
    """

    def __init__(self, f, maxsize=0, initial=io.DEFAULT_BUFFER_SIZE, factor=1.5, **kwargs):
        """Initialize a BufferedReader.

        f: the file to wrap.
        maxsize: int, maximum internal buffer size, 0=no limit.
        initial: int, initial buffer size.
        factor: float, the growth factor.
        """
        super(BufferedReader, self).__init__(f, **kwargs)
        self.buf = bytearray(initial)
        self.view = memoryview(self.buf)
        self.stop = 0
        self._readinto = getattr(self.f, 'readinto1', self.f.readinto)
        self.maxsize = maxsize
        self.factor = factor
        if factor <= 1:
            raise ValueError('Growth factor must be > 1')

    def _grow(self, target=None, constant=io.DEFAULT_BUFFER_SIZE):
        """Grow the buffer.

        Raise if would exceed maxsize.
        constant: growth constant.

        Buffer grows by max of factor and constant, capped by maxsize
        if applicable.
        """
        L = len(self.buf)
        if L == self.maxsize:
            raise ValueError('Read buffer too big.')
        if target is None or target <= L:
            target = max(int(L * self.factor), L + constant)
        else:
            minsize = L + constant
            while L < target:
                L = int(L * self.factor)
            target = max(L, minsize)
        if self.maxsize:
            self.buf = self.buf.ljust(min(target, self.maxsize))
        else:
            self.buf = self.buf.ljust(target)
        self.view = memoryview(self.buf)

    def extract(self, out, newstart):
        """Extract items from buffer into out.

        out: container
            Should support `append()`.
        newstart: int
            Index of start of new data.

        Unprocessed data should be in self.buf[:self.stop].
        Return the number of bytes parsed into objects.
        -1 if there was an irrecoverable error.
        grow if needed.
        """
        raise NotImplementedError

    def readinto1(self, out):
        amt = self._readinto(self.view[self.stop:])
        if amt:
            oldstop = self.stop
            self.stop += amt
            return self.extract(out, oldstop)
        elif amt is None:
            return None
        elif amt == 0:
            return -1
        else:
            raise ValueError('Unexpected readinto return value {}'.format(amt))

class Writer(FileWrapper):
    """Write objects."""
    def write(self, item):
        """Write a new item."""
        raise NotImplementedError

    def __bool__(self):
        """Return whether there is queued data to write."""
        return False

    def flush1(self):
        """Partial flush.  Return the number of flushed bytes.

        Other return values:
            None: would block (if non-blocking)
            -1: error (disconnected?)
        """
        raise NotImplementedError

    def flush(self):
        """Flush everything.

        Return None if would block. -1 if error.
        """
        raise NotImplementedError

    def detach(self):
        self.flush()
        ret = super(Writer, self).detach()
        return ret

class BWriter(Writer):
    """Write blocking.

    Blocking writing can be easier because there is no need to manage
    buffers for partial writes.  They can also be more performant
    compared to QWriter assuming you do not need to manage multiple
    writers in a single thread.  The given file object should be
    a io.BufferedIOBase or follow its semantics.
    """
    def flush(self):
        self.f.flush()
    flush1 = flush


class QWriter(Writer):
    """Write objects.

    Queue objects for writing.
    This may be a bit slower than writing directly and blocking, but can
    allow a single thread to handle multiple connections simultaneously.
    """
    def __init__(self, *args, **kwargs):
        super(QWriter, self).__init__(*args, **kwargs)
        self.q = collections.deque()

    def __bool__(self):
        """Return whether excess data exists."""
        return bool(self.q)

    def flush1(self):
        """Flush excess buffer and flush underlying file. Max write 1.

        Return the number of bytes flushed.  0 means no bytes were
        flushed because there were no bytes to flush.  None
        would mean that no bytes were flushed because it would have
        blocked (If wrapped file is in non-blocking mode).
        """
        if self.q:
            view = self.q[0]
            amt = self.f.write(view)
            view = view[amt:]
            if len(view):
                self.q[0] = view
            else:
                self.q.popleft()
                if not self.q:
                    self.f.flush()
            return amt
        else:
            return 0

    def flush(self):
        """Keep writing until all flushed.

        Stop if would block or error.
        Return the total number of bytes flushed.
        None if would block and no bytes flushed.
        """
        numflushed = 0
        while self.q:
            view = self.q[0]
            target = len(view)
            amt = 0
            while amt < target:
                try:
                    chunk = self.f.write(view[amt:])
                except EnvironmentError as e:
                    if e.errno in errnos.WOULDBLOCK:
                        self.q[0] = view[amt:]
                        return numflushed + amt or None
                    elif e.errno == errnos.EINTR:
                        chunk = 0
                    raise
                except Exception:
                    self.q[0] = view[amt:]
                    raise
                if chunk is None:
                    self.q[0] = view[amt:]
                    return numflushed + amt or None
                else:
                    amt += chunk
            numflushed += target
            self.q.popleft()
        self.f.flush()
        return numflushed
