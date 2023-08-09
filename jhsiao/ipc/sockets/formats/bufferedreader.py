__all__ = ['BufferedReader']
import io
import socket

from . import bases

class BufferedReader(bases.Buffered, bases.Reader):
    def __init__(self, f):
        """Initialize a BufferedReader."""
        super(BufferedReader, self).__init__(f)
        self._readinto = getattr(self.f, 'readinto1', self.f.readinto)

    def detach(self):
        ret = super(BufferedReader, self).detach()
        del self._readinto
        return ret

    def extract(self, out, newstart):
        """Extract items from buffer into out.

        Data should be maintained at the start of the buffer.

        out: container
            Should support `append()`.
        newstart: int
            Index of start of new data.

        Return the number of bytes parsed into objects.
        -1 if there was an irrecoverable error.
        grow if needed.
        """
        raise NotImplementedError

    def readinto1(self, out):
        try:
            amt = self._readinto(self.view[self.stop:])
        except Exception:
            return -1
        if amt == 0:
            return -1
        else:
            oldstop = self.stop
            self.stop += amt
            return self.extract(out, oldstop)
