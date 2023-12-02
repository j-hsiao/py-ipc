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

def line_iter(
    f, out, verbose=False, buffersize=io.DEFAULT_BUFFER_SIZE, end=b'\n',
    process=memoryview.tobytes):
    """Initialize a line-reading iterator on a file.

    buffersize: the initial buffersize to use.
    end: The line ending to use.
    process: A function to process the line stored in a memoryview.
    """
    tryread = base.tryreader(f.readinto, verbose)
    buf = bytearray(max(buffersize, 4))
    view = memoryview(buf)
    start = stop = 0
    while 1:
        amt = tryread(view[stop:])
        if amt is None or amt < 0:
            yield amt
            continue
        elif amt != 0:
            nstop = stop + amt
            pos = buf.find(end, stop, nstop)
            while pos >= 0:
                pos += len(end)
                out.append(process(view[start:pos]))
                start = pos
                pos = buf.find(end, start, nstop)
            stop = nstop
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
            yield amt
        else:
            if start < stop:
                out.append(process(view[start:stop]))
            start = stop = 0
            yield -1
