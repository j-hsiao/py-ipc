"""Data format that consists of a length followed by raw bytes.

The length is variable by the following scheme:
0-63: 1 byte length followed by data.
Otherwise
    1 byte: indicate length bytes
        64:  2 bytes
        128: 4 bytes
        192: 8 bytes
    N bytes: indicate length of chunk
    N bytes: the data.
"""
import collections
import struct

from . import gen

SINGLE = 0x3f
BYTE = struct.Struct('B')
RHEAD = [
    None,
    struct.Struct('H'),
    struct.Struct('L'),
    struct.Struct('Q')
]
WHEAD = [
    [struct.Struct('H'), 0xFFFF, 0x40],
    [struct.Struct('L'), 0xFFFFFFFF, 0x80],
    [struct.Struct('Q'), 0xFFFFFFFFFFFFFFFF, 0xC0],
]

def rprelen(poller, f):
    readall = gen.readall

    out = poller.out
    readinto = f.readinto

    MAX_HEAD = WHEAD[-1][0].size+1
    header = bytearray(MAX_HEAD)
    while 1:
        pass





class WPreLen(gen.WGen):
    def __init__(self, *args):
        super(WGen, self).__init__(*args)
        self.data = collections.deque()

    def write(self, data):
        length = len(data)
        if length <= SINGLE:
            buf = bytearray(length+1)
            buf[0] = length
            buf[1:length+1] = data
            self.data.append(buf)
            return length
        else:
            for fmt, size, code in WHEAD:
                if length <= size:
                    buf = bytearray(fmt.size+1)
                    buf[0] = code
                    fmt.pack_into(buf, 1, length)
                    self.data.append(buf)
                    self.data.append(data)
                    return length
            raise ValueError('Data length too large ({})'.format(length)

    def __iter__(self):
        fwrite = self.f.write
        d = self.deque
        headbuf = bytearray(0x40)
        while 1:
            try:
                data = self.deque.popleft()
            except IndexError:
                yield None
                # TODO: remove from writeables, no polling
            else:
                for item in gen.writeall(fwrite, data):
                    pass

