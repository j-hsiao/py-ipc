"""Read a chunk of a particular size."""
import io
import struct
import sys

from . import base


class GChunkReader(base.Reader):
    """Process chunks of bytes.

    _process() should be a callable with 1 argument, the bytes to
    process and defaults to memoryview.tobytes
    """
    _process = staticmethod(memoryview.tobytes)

    def _iter(self, buffersize=io.DEFAULT_BUFFER_SIZE, size='<Q'):
        """Iterator for parsing chunks of data.

        buffersize: size of the buffer.
        size: struct.Struct string for parsing the size of a chunk.
        """
        s = struct.Struct(size)
        buf = bytearray(max(buffersize, s.size))
        view = memoryview(buf)
        start = end = 0
        _process = self._process
        out = self.out
        while 1:
            target = start + s.size
            if target > len(buf):
                cursize = end - start
                view[:cursize] = view[start:end]
                start = 0
                end = cursize
                target = s.size
            while end < target:
                end += (yield view[end:])
            nbytes = s.unpack_from(buf, start)[0]
            start = target
            target = start + nbytes
            if target > len(buf):
                cursize = end - start
                if nbytes > len(buf):
                    buf = bytearray(nbytes + s.size)
                    buf[:cursize] = view[start:end]
                    view = memoryview(buf)
                else:
                    view[:cursize] = view[start:end]
                start = 0
                end = cursize
                target = nbytes
            while end < target:
                end += (yield view[end:])
            out.append(_process(view[start:target]))
            if end == target:
                start = end = 0
            else:
                start = target

def chunk_iter(
    f, out, verbose=False,
    buffersize=io.DEFAULT_BUFFER_SIZE, size='<Q',
    process=memoryview.tobytes):
    """Iterator for parsing chunks of data.

    buffersize: size of the buffer.
    size: struct.Struct string for parsing the size of a chunk.
    """
    tryread = base.tryreader(f.readinto, verbose)
    s = struct.Struct(size)
    buf = bytearray(max(buffersize, s.size))
    view = memoryview(buf)
    start = end = 0
    out = out
    while 1:
        target = start + s.size
        if target > len(buf):
            cursize = end - start
            view[:cursize] = view[start:end]
            start = 0
            end = cursize
            target = s.size
        while end < target:
            amt = tryread(view[end:])
            if amt is None or amt < 0:
                yield amt
            elif amt > 0:
                end += amt
                yield amt
            else:
                yield -1
        nbytes = s.unpack_from(buf, start)[0]
        start = target
        target = start + nbytes
        if target > len(buf):
            cursize = end - start
            if nbytes > len(buf):
                buf = bytearray(nbytes + s.size)
                buf[:cursize] = view[start:end]
                view = memoryview(buf)
            else:
                view[:cursize] = view[start:end]
            start = 0
            end = cursize
            target = nbytes
        while end < target:
            amt = tryread(view[end:])
            if amt is None or amt < 0:
                yield amt
            elif amt > 0:
                end += amt
                yield amt
            else:
                yield -1
        out.append(process(view[start:target]))
        if end == target:
            start = end = 0
        else:
            start = target

if sys.version_info >= (3,3):
    from .gchunktest3 import chunk_iter2
else:
    def chunk_iter2(
        f, out, verbose=False,
        buffersize=io.DEFAULT_BUFFER_SIZE, size='<Q',
        process=memoryview.tobytes):
        """Iterator for parsing chunks of data.

        buffersize: size of the buffer.
        size: struct.Struct string for parsing the size of a chunk.
        """
        readinto = f.readinto
        tryread = base.tryreader(f.readinto, verbose)
        s = struct.Struct(size)
        buf = bytearray(max(buffersize, s.size))
        view = memoryview(buf)
        start = end = 0
        out = out
        while 1:
            target = start + s.size
            if target > len(buf):
                cursize = end - start
                view[:cursize] = view[start:end]
                start = 0
                end = cursize
                target = s.size
            if end < target:
                p = [end]
                for _ in base.readtil(readinto, view, p, target):
                    yield _
                end = p[0]
            nbytes = s.unpack_from(buf, start)[0]
            start = target
            target = start + nbytes
            if target > len(buf):
                cursize = end - start
                if nbytes > len(buf):
                    buf = bytearray(nbytes + s.size)
                    buf[:cursize] = view[start:end]
                    view = memoryview(buf)
                else:
                    view[:cursize] = view[start:end]
                start = 0
                end = cursize
                target = nbytes
            if end < target:
                p = [end]
                for _ in base.readtil(readinto, view, p, target):
                    yield _
                end = p[0]
            out.append(process(view[start:target]))
            if end == target:
                start = end = 0
            else:
                start = target

def chunk_iter3(
    f, out, verbose=False,
    buffersize=io.DEFAULT_BUFFER_SIZE, size='<Q',
    process=memoryview.tobytes):
    """Iterator for parsing chunks of data.

    buffersize: size of the buffer.
    size: struct.Struct string for parsing the size of a chunk.
    """
    readtils = base.readtilsend(f.readinto)
    next(readtils)
    tryread = base.tryreader(f.readinto, verbose)
    s = struct.Struct(size)
    buf = bytearray(max(buffersize, s.size))
    view = memoryview(buf)
    start = end = 0
    out = out
    while 1:
        target = start + s.size
        if target > len(buf):
            cursize = end - start
            view[:cursize] = view[start:end]
            start = 0
            end = cursize
            target = s.size
        if end < target:
            v = readtils.send((view, end, target))
            while v or v is None:
                yield v
                v = next(readtils)
            end = next(readtils)
            if end < target:
                yield -1
        nbytes = s.unpack_from(buf, start)[0]
        start = target
        target = start + nbytes
        if target > len(buf):
            cursize = end - start
            if nbytes > len(buf):
                buf = bytearray(nbytes + s.size)
                buf[:cursize] = view[start:end]
                view = memoryview(buf)
            else:
                view[:cursize] = view[start:end]
            start = 0
            end = cursize
            target = nbytes
        if end < target:
            v = readtils.send((view, end, target))
            while v or v is None:
                yield v
                v = next(readtils)
            end = next(readtils)
            if end < target:
                yield -1
        out.append(process(view[start:target]))
        if end == target:
            start = end = 0
        else:
            start = target

def chunk_iter4(
    f, out, verbose=False,
    buffersize=io.DEFAULT_BUFFER_SIZE, size='<Q',
    process=memoryview.tobytes):
    """Iterator for parsing chunks of data.

    buffersize: size of the buffer.
    size: struct.Struct string for parsing the size of a chunk.
    """
    readinto = f.readinto
    s = struct.Struct(size)
    buf = bytearray(max(buffersize, s.size))
    view = memoryview(buf)
    start = end = 0
    out = out
    while 1:
        target = start + s.size
        if target > len(buf):
            cursize = end - start
            view[:cursize] = view[start:end]
            start = 0
            end = cursize
            target = s.size
        while end < target:
            try:
                amt = readinto(view[end:])
            except EnvironmentError as e:
                if e.errno in errnos.WOULDBLOCK:
                    yield None
                elif e.errno != errnos.EINTR:
                    if verbose:
                        traceback.print_exc()
                    yield -1
            except Exception:
                if verbose:
                    traceback.print_exc()
                yield -1
            else:
                if amt is None:
                    yield amt
                elif amt > 0:
                    end += amt
                    yield amt
                else:
                    yield -1
        nbytes = s.unpack_from(buf, start)[0]
        start = target
        target = start + nbytes
        if target > len(buf):
            cursize = end - start
            if nbytes > len(buf):
                buf = bytearray(nbytes + s.size)
                buf[:cursize] = view[start:end]
                view = memoryview(buf)
            else:
                view[:cursize] = view[start:end]
            start = 0
            end = cursize
            target = nbytes
        while end < target:
            try:
                amt = readinto(view[end:])
            except EnvironmentError as e:
                if e.errno in errnos.WOULDBLOCK:
                    yield None
                elif e.errno != errnos.EINTR:
                    if verbose:
                        traceback.print_exc()
                    yield -1
            except Exception:
                if verbose:
                    traceback.print_exc()
                yield -1
            else:
                if amt is None:
                    yield amt
                elif amt > 0:
                    end += amt
                    yield amt
                else:
                    yield -1
        out.append(process(view[start:target]))
        if end == target:
            start = end = 0
        else:
            start = target
