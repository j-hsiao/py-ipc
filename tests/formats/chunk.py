import io
import struct

from jhsiao.ipc.sockets.formats import chunk

data = [b'hello world', b'goodbye\nwhatever']
vals = []
for item in data:
    L = len(item)
    pick = chunk.bitlen_idx[L.bit_length()]
    vals.append(chunk.encodes[pick].pack(pick, L) + item)

def test_reader_basic():
    with chunk.Reader(io.BytesIO(vals[0])) as f:
        objs = []
        amt = f.readinto1(objs)
        assert amt > 0
        assert f.readinto1(objs) < 0
        assert objs[0] == data[0]
        assert amt == f.f.tell()

    with chunk.Reader(io.BytesIO(vals[0] + vals[1])) as f:
        objs = []
        amt = f.readinto(objs)
        assert amt == f.f.tell()
        assert f.readinto(objs) < 0
        assert objs[0] == data[0]
        assert objs[1] == data[1]


def test_reader_split():
    with io.BytesIO(vals[0][:1]) as buf:
        with chunk.Reader(buf) as f:
            objs = []
            assert f.readinto1(objs) == 0
            assert f.readinto1(objs) < 0
            assert not objs

            cur = buf.tell()
            buf.write(vals[0][1:5])
            buf.seek(cur)
            assert f.readinto1(objs) == 0
            assert f.readinto1(objs) < 0

            cur = buf.tell()
            buf.write(vals[0][5:7])
            buf.seek(cur)
            assert f.readinto1(objs) == 0
            assert f.readinto1(objs) < 0

            cur = buf.tell()
            buf.write(vals[0][7:])
            buf.seek(cur)
            amt = f.readinto1(objs)
            assert amt > 0
            assert f.readinto1(objs) < 0
            assert objs[0] == data[0]
            assert amt == buf.tell()

    with io.BytesIO(vals[0] + vals[1][:1]) as buf:
        with chunk.Reader(buf) as f:
            objs = []
            amt = f.readinto(objs)
            assert amt > 0
            assert f.readinto(objs) < 0
            assert objs[0] == data[0]

            cur = buf.tell()
            buf.write(vals[1][1:])
            buf.seek(cur)
            amt2 = f.readinto(objs)
            assert amt2 > 0
            assert f.readinto(objs) < 0
            assert objs[1] == data[1]
            assert amt + amt2 == buf.tell()

def test_reader_multisplit():
    with io.BytesIO(vals[0][:1]) as buf:
        buf.write(vals[0])
        buf.write(vals[1][:1])
        buf.seek(0)
        with chunk.Reader(buf) as f:
            objs = []
            amt = f.readinto1(objs)
            assert amt > 0
            assert f.readinto1(objs) < 0
            assert objs[0] == data[0]

            objs = []
            cur = buf.tell()
            buf.write(vals[1][1:5])
            buf.seek(cur)
            assert f.readinto1(objs) == 0
            assert f.readinto1(objs) < 0

            cur = buf.tell()
            buf.write(vals[1][5:7])
            buf.seek(cur)
            assert f.readinto1(objs) == 0
            assert f.readinto1(objs) < 0

            cur = buf.tell()
            buf.write(vals[1][7:])
            buf.seek(cur)
            amt2 = f.readinto1(objs)
            assert amt2 > 0
            assert f.readinto1(objs) < 0
            assert objs[0] == data[1]
            assert amt + amt2 == buf.tell()



def test_writer():
    buf = io.BytesIO()
    with chunk.BWriter(buf) as f:
        data = b'hello'
        f.write(data)
        assert not f
        ser = buf.getvalue()
        assert struct.unpack_from('>BB', ser) == (0, len(data))
        assert ser[2:] == data


    class dummy(object):
        def __init__(self, f):
            self.f = f
        def write(self, d):
            if len(d):
                self.f.write(d[:1])
                return 1
            return 0
        def flush(self):
            pass
        def close(self):
            pass

    with chunk.QWriter(dummy(io.BytesIO())) as f:
        data = b'hello'
        f.write(data)
        assert f
        while f:
            assert f.flush1()

        ser = f.f.f.getvalue()
        assert struct.unpack_from('>BB', ser) == (0, len(data))
        assert ser[2:] == data
