"""Read a chunk of a particular size.

"""
import io
import struct

class ChunkReader(object):
    _process = staticmethod(memoryview.tobytes)

    def read(self, out, buffersize=io.DEFAULT_BUFFER_SIZE, size='<Q'):
        s = struct.Struct(size)
        buf = bytearray(max(io.DEFAULT_BUFFER_SIZE, s.size))
        view = memoryview(buf)
        start = end = 0
        _process = self._process
        while 1:
            target = start + s.size
            if target > len(buf):
                cursize = end - start
                view[:cursize] = view[start:end]
                start = 0
                end = size
                target = s.size
            while end < target:
                amt = yield view[end:]
                if amt:
                    end += amt
                else:
                    yield None
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
                amt = yield view[end:]
                if amt:
                    end += amt
                else:
                    yield None
            out.append(_process(view[start:target]))
            start = target


if __name__== '__main__':
    out = []
    r = ChunkReader()
    it = r.read(out)
    buf = next(it)
    with io.BytesIO() as dummy:
        messages = [b'hello', b'world', b'hello world']
        for msg in messages:
            dummy.write(struct.pack('<Q', len(msg)))
            dummy.write(msg)
        dummy.seek(0)
        while buf is not None:
            buf = it.send(dummy.readinto(buf[:3]))
        print(out)
