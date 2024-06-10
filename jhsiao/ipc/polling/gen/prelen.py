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
import io
import struct

from . import gen

SINGLE = 0x3f
BYTE = struct.Struct('B')
RHEAD = [
    None,
    struct.Struct('>H'),
    struct.Struct('>L'),
    struct.Struct('>Q')
]
WHEAD = [
    [struct.Struct('>H'), 0xFFFF, 0x40],
    [struct.Struct('>L'), 0xFFFFFFFF, 0x80],
    [struct.Struct('>Q'), 0xFFFFFFFFFFFFFFFF, 0xC0],
]

class VPreLen(gen.Gen):
    """Read and write data with variable data length prefix.

    This has lower bandwidth for many short messages but slower parsing.

    1 byte:
        0-63: following data is 0-63 bytes
        64 : next 2 bytes is length of data
        128: next 4 bytes is length of data
        192: next 8 bytes is length of data
    """
    def readloop(self):
        readall = gen.readall

        out = poller.out
        readinto = f.readinto

        MAX_HEAD = WHEAD[-1][0].size+1
        header = bytearray(MAX_HEAD)
        while 1:
            pass

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
            raise ValueError('Data length too large ({})'.format(length))

Q = struct.Struct('>Q')
L = struct.Struct('>L')
H = struct.Struct('>H')
B = struct.Struct('>B')
class FPreLen(gen.Gen):
    """Read and write data with 8 bytes of length.

    This will have larger bandwidth for reasonably sized messages but
    faster parsing.
    """
    def __init__(self, poller, f, fmt=Q):
        super(FPreLen, self).__init__(poller, f)
        self.fmt = fmt

    def readloop(self):
        try:
            poller = self.poller
            fmt = self.fmt
            fill_buf = poller.fill_buf
            readinto = f.readinto
            DEFAULT_BUFFER_SIZE = io.DEFAULT_BUFFER_SIZE
            buf = memoryview(bytearray(DEFAULT_BUFFER_SIZE))
            header = bytearray(MAX_HEAD)
            headersize = self.fmt.size
            fd = self.fileno()
            wrapped = poller.resources[fd]
            datastart = dataend = 0
            while 1:
                if dataend - datastart < headersize:
                    target = datastart + headersize
                    if target > DEFAULT_BUFFER_SIZE:
                        extra = buf[datastart:dataend]
                        dataend -= datastart
                        buf[:dataend] = extra
                        datastart = 0
                        target = headersize
                    for amt in fill_buf(fd, readinto, buf[dataend:], headersize):
                        yield
                    dataend += amt
                msgsize = fmt.unpack_from(buf, datastart)[0]
                datastart += headersize
                target = datastart + msgsize
                if target > DEFAULT_BUFFER_SIZE:
                    if target > DEFAULT_BUFFER_SIZE:
                        out = memoryview(bytearray(msgsize))
                        current = dataend-datastart
                        out[:current] = buf[datastart:dataend]
                        for amt in fill_buf(fd, readinto, out[dataend-datastart:], msgsize-current):
                            yield
                        with poller.lock:
                            poller.out.append((wrapped, out))
                        dataend = datastart = 0
                        continue
                    else:
                        extra = buf[datastart:dataend]
                        dataend -= datastart
                        buf[:dataend] = extra
                        datastart = 0
                        target = msgsize
                if dataend < target:
                    for amt in fill_buf(fd, readinto, out[dataend:], target-dataend):
                        yield
                    dataend += amt
                with poller.lock:
                    poller.out.append((wrapped, buf[datastart:target].tobytes()))
                datastart = target
        except Exception:
            self.poller.read_error(self.f.fileno())

    def write(self, data):
        dq = self.dataq
        with self.poller.lock:
            self.poller.tasks.append((
                self.poller.enqueue_write,
                (self.fileno(), dq, dq.extend,
                (self.fmt.pack(len(data)), data))))
        self.poller.control.write(b' ')
