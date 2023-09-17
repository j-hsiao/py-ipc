"""Serial pickles.

This format is very easy to write because you just pickle.dump into
the stream.  However, reading can have bad worst-case performance where
data is read in chunks but every chunk contains `pickle.STOP`.  Every
small chunk leads to an attempt to unpickle which will usually fail
because the entire object has not been transferred yet.  This format is
probably still be faster than chunked if objects are small or most
objects do not contain `pickle.STOP` in its serialization.
"""
__all__ = ['Reader', 'Writer', 'QWriter']
import io
import pickle

from . import bases, viewreader

class Reader(bases.BufferedReader):
    """Read serial pickles."""

    def extract(self, out, newstart):
        # In the case of partial reads, every unpickling attempt
        # resulting in error results in high overhead.
        # Searching for pickle.STOP results in lower average
        # timing.
        if self.buf.find(pickle.STOP, newstart, self.stop) < 0:
            if self.stop == len(self.buf):
                try:
                    self._grow()
                except (ValueError, MemoryError):
                    return -1
            return 0
        start = 0
        with viewreader.ViewReader(self.view[:self.stop]) as f:
            try:
                while start < self.stop:
                    out.append(pickle.load(f))
                    start = f.pos
            except Exception:
                pass
        if start:
            if start == self.stop:
                self.stop = 0
            else:
                trail = self.view[start:self.stop]
                self.stop -= start
                self.view[:self.stop] = trail
        elif self.stop == len(self.buf):
            try:
                self._grow()
            except (ValueError, MemoryError):
                return -1
        return start

class BWriter(bases.BWriter):
    def write(self, item):
        pickle.dump(item, self.f)

    def flush(self):
        self.f.flush()

class QWriter(bases.QWriter):
    def write(self, item):
        self.q.append(pickle.dumps(item))
