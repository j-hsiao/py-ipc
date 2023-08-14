"""Read line by line."""
__all__ = ['Reader', 'BWriter', 'QWriter']
import codecs
import sys

from . import bases

_utf8_decode = codecs.getdecoder('utf8')
_parse_binary = memoryview.tobytes
def _parse_text(view):
    return _utf8_decode(view)[0]

class Reader(bases.BufferedReader):
    """Read line by line."""

    def __init__(self, f, mode='rb'):
        """Initialize line format reader.

        mode: str
            Determine the mode.  If it contains 's' then use str mode
            (binary if py2, else text).  If it contains 'b' then use
            binary mode (str in py2 else bytes).  Otherwise, use text
            mode (unicode in py2, else str).
        Only utf-8 encoding is supported for text mode.
        """
        super(Reader, self).__init__(f)
        if 's' in mode:
            if sys.version_info.major > 2:
                self.parse = _parse_text
            else:
                self.parse = _parse_binary
        elif 'b' in mode:
            self.parse = _parse_binary
        else:
            self.parse = _parse_text

    def extract(self, out, newstart):
        stop = self.stop
        view = self.view
        nl = self.buf.find(b'\n', newstart, stop)
        start = 0
        while 0 <= nl < stop:
            end = nl+1
            out.append(self.parse(view[start:end]))
            start = end
            nl = self.buf.find(b'\n', start, stop)
        if start:
            if start == stop:
                self.stop = 0
            else:
                trail = view[start:stop]
                stop -= start
                view[:stop] = trail
                self.stop = stop
        elif stop == len(self.buf):
            try:
                self._grow()
            except (ValueError, MemoryError):
                return -1
        return start

    def readinto1(self, out):
        try:
            amt = self._readinto(self.view[self.stop:])
        except EnvironmentError as e:
            if e.errno == EAGAIN or e.errno == EWOULDBLOCK:
                return None
            raise
        # non-blocking, still valid.
        if amt:
            oldstop = self.stop
            self.stop += amt
            return self.extract(out, oldstop)
        elif amt is None:
            return None
        elif amt == 0:
            if self.stop:
                out.append(self.parse(self.view[:self.stop]))
                ret = self.stop
                self.stop = 0
                return ret
            else:
                return -1
        else:
            raise ValueError('Unexpected readinto return value {}'.format(amt))


class BWriter(bases.BWriter):
    """Write lines blocking.

    User must add newline to each item to write.
    Otherwise, it will be merged.
    """
    def __init__(self, *args, **kwargs):
        super(BWriter, self).__init__(*args, **kwargs)
        self.write = self.f.write

    def write(self, item):
        return self.write(item)

class QWriter(bases.QWriter):
    """Write lines non-blocking buffered.

    User must add newline to each item to write.
    Otherwise, it will be merged.
    """
    def write(self, item):
        self.q.append(item)
