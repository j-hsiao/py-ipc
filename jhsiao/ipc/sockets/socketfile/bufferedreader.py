__all__ = ['BufferedReader']
import io
import socket
import traceback

from socketfile import bases

class BufferedReader(bases.Reader):
    def __init__(self, f):
        """Initialize a BufferedReader."""
        super(BufferedReader, self).__init__(f)
        self.buf = bytearray(io.DEFAULT_BUFFER_SIZE)
        self.view = memoryview(self.buf)
        self.stop = 0
        self._readinto = getattr(self.f, 'readinto1', self.f.readinto)

    def extract(self, out, newstart):
        """Extract items from buffer into out.

        out: container
            Should support `append()`.
        newstart: int
            Index of start of new data.
        Return the amount of consumed data and should reset
        data position at 0.
        """
        raise NotImplementedError

    def grow(self):
        """Grow buffer if an object was too big to fit in buffer."""
        newbuf = bytearray(int(len(self.buf) * 1.5))
        newview = memoryview(newbuf)
        newview[:self.stop] = self.view[:self.stop]
        self.buf = newbuf
        self.view = newview

    def read(self, out):
        """Read a little data.  Add parsed objects to out.

        Only a single syscall read is performed if the wrapped file
        object supports it.  This allows a server to service multiple
        connections simultaneously instead of potentially blocking on
        a single source.  As a result, there is no guarantee on the
        number of objects added to out.

        Return bool: whether the connection is still good.  The
        connection is still good if EOF is not reached and no exceptions
        (besides timeout) occurs.
        """
        try:
            amt = self._readinto(self.view[self.stop:])
        except socket.timeout:
            return True
        except Exception:
            traceback.print_exc()
            return False
        if amt == 0:
            print('empty read')
            return False
        else:
            oldstop = self.stop
            self.stop += amt
            if self.extract(out, oldstop):
                return True
            elif self.stop == len(self.buf):
                try:
                    self.grow()
                except Exception:
                    traceback.print_exc()
                    return False
            return True
