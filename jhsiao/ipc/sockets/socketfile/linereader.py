"""Read lines. (delimited by '\n')"""
__all__ = ['LineReader']
from socketfile import bufferedreader
import sys

class LineReader(bufferedreader.BufferedReader):
    """Read bytes lines."""
    def __init__(self, f, mode='rb'):
        """Initialize line reader.

        f: the file to wrap.
        mode: str
            The mode to use.  It is searched for specific characters.
            's': Use str
            'b': Use binary (str in py2, bytes in py3)
            else: Use text (unicode in py2, bytes in py3)
        """

        super(LineReader, self).__init__(f)
        if sys.version_info.major > 2:
            pass
        else:
            pass
        if 's' in mode:
            if sys.version_info.major > 2:
                self.extract = self._extract_text
            else:
                self.extract = self._extract_binary
        elif 'b' in mode:
            self.extract = self._extract_binary
        else:
            self.extract = self._extract_text

   def extract(self, out, newstart):
       return self.extract(out, newstart)

    def _extract_binary(self, out, newstart):
        nl = self.buf.find(b'\n', newstart, self.stop)
        start = 0
        while nl >= 0:
            out.append(self.view[start:].tobytes())
            start = nl+1
            nl = self.buf.find(b'\n', start, self.stop)
        if start:
            if start == self.stop:
                self.stop = 0
            else:
                trail = self.view[start:self.stop]
                self.stop = len(trail)
                self.view[:self.stop] = trail
        return start

    def _extract_text(self, out, newstart):
        nl = self.buf.find(b'\n', newstart, self.stop)
        start = 0
        while 0 <= nl < self.stop:
            try:
                out.append(codecs.decode(self.view[start:], 'utf8'))
            except UnicodeDecodeError:
                nl = self.buf.find(b'\n', nl+1, self.stop)
            else:
                start = nl+1
                nl = self.buf.find(b'\n', start, self.stop)
        if start:
            if start == self.stop:
                self.stop = 0
            else:
                trail = self.view[start:self.stop]
                self.stop = len(trail)
                self.view[:self.stop] = trail
        return start
