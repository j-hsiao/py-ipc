import io
import struct

from jhsiao.ipc.formats.stream import line

data = [b'hello world\n', b'goodbye\nwhatever']
text = ['hello world\n', 'goodbye\nwhatever']

def test_reader_basic():
    with line.Reader(io.BytesIO(data[0])) as f:
        objs = []
        amt = f.readinto1(objs)
        assert amt > 0
        assert f.readinto1(objs) < 0
        assert objs[0][0] is f
        assert objs[0][1] == data[0]
        assert amt == f.f.tell()

    with line.Reader(io.BytesIO(data[0]), 'r') as f:
        objs = []
        amt = f.readinto1(objs)
        assert amt > 0
        assert f.readinto1(objs) < 0
        assert objs[0][0] is f
        assert objs[0][1] == text[0]
        assert amt == f.f.tell()

    with line.Reader(io.BytesIO(data[0] + data[1])) as f:
        objs = []
        assert f.readinto(objs)
        assert f.readinto(objs) > 0
        assert f.readinto(objs) < 0
        assert objs == [(f, b'hello world\n'), (f, b'goodbye\n'), (f, b'whatever')]

    with line.Reader(io.BytesIO(data[0] + data[1]), 'r') as f:
        objs = []
        assert f.readinto(objs)
        assert f.readinto(objs) > 0
        assert f.readinto(objs) < 0
        assert objs == [(f, u'hello world\n'), (f, u'goodbye\n'), (f, u'whatever')]

def test_reader_split():
    with io.BytesIO(data[0][:1]) as buf:
        with line.Reader(buf) as f:
            objs = []
            assert f.readinto1(objs) == 0
            assert not objs

            cur = buf.tell()
            buf.write(data[0][1:5])
            buf.seek(cur)
            assert f.readinto1(objs) == 0
            assert not objs

            cur = buf.tell()
            buf.write(data[0][5:7])
            buf.seek(cur)
            assert f.readinto1(objs) == 0
            assert not objs

            cur = buf.tell()
            buf.write(data[0][7:])
            buf.seek(cur)
            amt = f.readinto1(objs)
            assert amt > 0
            assert f.readinto1(objs) < 0
            assert objs[0][0] is f
            assert objs[0][1] == data[0]
            assert amt == buf.tell()

    with io.BytesIO(data[0] + data[1][:1]) as buf:
        with line.Reader(buf) as f:
            objs = []
            amt = f.readinto(objs)
            assert amt > 0
            assert objs[0][1] == data[0]
            assert objs[0][0] is f

            cur = buf.tell()
            buf.write(data[1][1:])
            buf.seek(cur)
            amt2 = f.readinto(objs)
            assert amt2 > 0
            amt3 = f.readinto(objs)
            assert amt3 > 0
            assert objs[1:] == [(f, line) for line in data[1].splitlines(keepends=True)]
            assert amt + amt2 + amt3 == buf.tell()

def test_reader_multisplit():
    with io.BytesIO() as buf:
        buf.write(data[0])
        buf.write(data[1][:1])
        buf.seek(0)
        with line.Reader(buf) as f:
            objs = []
            amt = f.readinto1(objs)
            assert amt > 0
            assert objs[0] == (f, data[0])

            objs = []
            cur = buf.tell()
            buf.write(data[1][1:5])
            buf.seek(cur)
            assert f.readinto1(objs) == 0

            cur = buf.tell()
            buf.write(data[1][5:8])
            buf.seek(cur)
            amt2 = f.readinto1(objs)
            assert amt2 > 0
            assert objs[0] == (f, b'goodbye\n')

            objs = []
            cur = buf.tell()
            buf.write(data[1][8:])
            buf.seek(cur)
            assert f.readinto1(objs) == 0
            amt3 = f.readinto1(objs)
            assert amt3 > 0
            assert f.readinto1(objs) < 0
            assert objs[0] == (f, b'whatever')
            assert amt + amt2 + amt3 == buf.tell()



def test_writer():
    buf = io.BytesIO()
    with line.BWriter(buf) as f:
        data = b'hello'
        f.write(data)
        assert not f
        ser = buf.getvalue()
        assert buf.getvalue() == data

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

    with line.QWriter(dummy(io.BytesIO())) as f:
        data = b'hello'
        f.write(data)
        assert f
        while f:
            assert f.flush1()

        ser = f.f.f.getvalue()
        assert ser == data
