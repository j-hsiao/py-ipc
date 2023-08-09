"""Basic classes.

These classes are more oriented towards
sending/receiving entire objects.
"""
__all__ = ['FileWrapper', 'Reader', 'Writer']

import io

class FileWrapper(object):
    def __init__(self, f):
        self.f = f

    def fileno(self):
        return self.f.fileno()

    def detach(self):
        ret = self.f
        self.f = None
        return ret

    def close(self):
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
        """
        raise NotImplementedError

    def readinto(self, out):
        """Call readinto1 until at least 1 object is read or eof."""
        result = self.readinto1(out)
        while result == 0:
            result = self.readinto1(out)
        return result

    def read(self):
        """Same as readinto(), but return a new list.

        Also return the readinto count because no other way
        to tell whether partial read or eof.
        """
        L = []
        return L, self.readinto(L)

class Buffered(object):
    """A class that maintains a buffer that can grow."""
    # TODO Maybe add a limit for the buffer?
    def __init__(self, *args, **kwargs):
        super(Buffered, self).__init__(*args, **kwargs)
        self.buf = bytearray(io.DEFAULT_BUFFER_SIZE)
        self.view = memoryview(self.buf)
        self.stop = 0

    def _grow(self):
        """Grow the buffer."""
        self.buf = self.buf.ljust(int(len(self.buf) * 1.5))
        self.view = memoryview(self.buf)

class Writer(FileWrapper):
    """Write objects.

    This expects an io.BufferedIOBase (blocking and buffered writes).
    No partial writes allowed.
    """
    def write(self, item):
        """Write a new item."""
        raise NotImplementedError

    def flush(self):
        self.f.flush()

    def detach(self):
        ret = super(BufferedWriter).detach()
        self.flush()
        return ret

class BufferedWriter(Buffered, Writer):
    """Write objects.

    This allows partial object writes and so must buffer any excess
    data.  This is more helpful to allow a single thread to handle
    writes to multiple writers.
    """
    def __init__(self, *args, **kwargs):
        super(BufferedWriter, self).__init__(*args, **kwargs)
        self.start = 0

    def __bool__(self):
        """Return whether excess data exists."""
        return self.start < self.stop

    def flush1(self):
        """Flush excess buffer and flush underlying file. max write 1."""
        if self.start < self.stop:
            self.start += self.f.write(self.view[self.start:self.stop])
            if self.start == self.stop:
                self.f.flush()
        else:
            self.f.flush()

    def flush(self):
        """Keep writing until all flushed."""
        while self.start < self.stop:
            self.start += self.f.write(self.view[self.start:self.stop])
        self.f.flush()
