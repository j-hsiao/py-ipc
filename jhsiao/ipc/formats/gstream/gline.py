"""Read til line end (delimiter)."""
import io

from . import base

class GLineReader(base.Reader):
    _process = staticmethod(memoryview.tobytes)

    def _iter(self, buffersize=io.DEFAULT_BUFFER_SIZE, end=b'\n'):
        buf = bytearray(max(buffersize, 2))
        view = memoryview(buf)
        start = stop = 0
        process = self._process
        out = self.out
        while 1:
            nstop = stop + (yield view[stop:])
            if stop == nstop:
                while stop == nstop:
                    if start < stop:
                        out.append(process(view[start:stop]))
                    start = stop = 0
                    nstop = yield view
            pos = buf.find(end, stop, nstop)
            while pos >= 0:
                pos += len(end)
                out.append(process(view[start:pos]))
                start = pos
                pos = buf.find(end, start, nstop)
            stop = nstop
            #shift or resize
            if stop == len(buf):
                if start == 0:
                    buf = bytearray(int(len(buf) * 1.5))
                    buf[:stop] = view
                    view = memoryview(buf)
                else:
                    nstop = stop-start
                    view[:nstop] = view[start:stop]
                    stop = nstop
                    start = 0
