"""Size followed by data.

1 byte: size code
S bytes: size of data
N bytes: data

Data is read/written as bytes or bytes-like objects.
"""
__all__ = ['Reader', 'BWriter', 'QWriter']
import io
import struct

encodes = [
    struct.Struct('>BB'),
    struct.Struct('>BH'),
    struct.Struct('>BL'),
    struct.Struct('>BQ'),
]

decodes = [
    struct.Struct('>B'),
    struct.Struct('>H'),
    struct.Struct('>L'),
    struct.Struct('>Q'),
]

from . import bases

def bitlen_idx():
    idx = []
    current = 0
    for i in range(65):
        while i > decodes[current].size*8:
            current += 1
        idx.append(current)
    return idx
bitlen_idx = bitlen_idx()


class Reader(bases.Reader):
    """Return bytearray or bytes"""
    def __init__(self, f):
        super(Reader, self).__init__(f)
        self.sizebuf = bytearray(io.DEFAULT_BUFFER_SIZE)
        self.pos = 0
        self.view = memoryview(self.sizebuf)
        self._readinto = getattr(self.f, 'readinto1', self.f.readinto)
        self.partial = None
        self.pview = None
        self.pre = 0

    def readinto1(self, out):
        if self.partial is None:
            view = self.view
            try:
                amt = self._readinto(view[self.pos:])
            except EnvironmentError as e:
                if e.errno == bases.EAGAIN or e.errno == bases.EWOULDBLOCK:
                    return None
                raise
            if amt:
                pos = self.pos + amt
                start = 0
                while start < pos:
                    pick = decodes[decodes[0].unpack_from(view, start)[0]]
                    size_start = start + 1
                    size_end = size_start + pick.size
                    if size_end > pos:
                        if start:
                            chunk = view[start:pos]
                            pos -= start
                            view[:pos] = chunk
                        self.pos = pos
                        return start
                    else:
                        length = pick.unpack(view[size_start:size_end])[0]
                        data_end = size_end + length
                        if data_end <= pos:
                            out.append(view[size_end:data_end].tobytes())
                            start = data_end
                        else:
                            self.pre = size_end - start
                            self.partial = bytearray(length)
                            chunk = view[size_end:pos]
                            pos -= size_end
                            self.partial[:pos] = chunk
                            self.pview = memoryview(self.partial)[pos:]
                            self.pos = 0
                            return start
                self.pos = 0
                return start
            elif amt is None:
                return None
            elif amt == 0:
                return -1
        else:
            try:
                amt = self._readinto(self.pview)
            except EnvironmentError as e:
                if e.errno == bases.EAGAIN or e.errno == bases.EWOULDBLOCK:
                    return None
                raise
            if amt:
                remain = self.pview[amt:]
                if len(remain):
                    self.pview = remain
                    return 0
                else:
                    p = self.partial
                    out.append(self.partial)
                    self.partial = self.pview = None
                    return len(p) + self.pre
            elif amt is None:
                return None
            elif amt == 0:
                return -1

    def readinto(self, out):
        while self.partial is None:
            result = self.readinto1(out)
            if result or result is None:
                return result
        view = self.pview
        total = len(view)
        amt = 0
        try:
            while amt < total:
                chunk = self._readinto(view[amt:])
                if chunk:
                    amt += chunk
                elif chunk is None:
                    return None
                elif chunk == 0:
                    return -1
            out.append(self.partial)
            p = self.partial
            self.partial = self.pview = None
            return len(p) + self.pre
        except EnvironmentError as e:
            if e.errno == bases.EAGAIN or e.errno == bases.EWOULDBLOCK:
                return None
            raise

class BWriter(bases.BWriter):
    def write(self, data):
        L = len(data)
        pick = bitlen_idx[L.bit_length()]
        self.f.write(encodes[pick].pack(pick, L))
        self.f.write(data)

class QWriter(bases.QWriter):
    def write(self, data):
        L = len(data)
        pick = bitlen_idx[L.bit_length()]
        self.q.append(encodes[pick].pack(pick, L))
        self.q.append(data)
