import io
import pickle
import struct
import timeit

from jhsiao.ipc.formats.stream import chunkpkl, chunk

data = [b'hello world', b'goodbye\nwhatever']
vals = []
for item in data:
    item = pickle.dumps(item)
    L = len(item)
    pick = chunk.bitlen_idx[L.bit_length()]
    vals.append(chunk.encodes[pick].pack(pick, L) + item)


def test_reader_basic():
    with chunkpkl.Reader(io.BytesIO(vals[0])) as f:
        objs = []
        amt = f.readinto1(objs)
        assert amt > 0
        assert f.readinto1(objs) < 0
        assert objs[0][0] is f
        assert objs[0][1] == data[0]
        assert amt == f.f.tell()

    with chunkpkl.Reader(io.BytesIO(vals[0] + vals[1])) as f:
        objs = []
        amt = f.readinto(objs)
        assert amt == f.f.tell()
        assert f.readinto(objs) < 0
        assert objs[0][0] is f
        assert objs[0][1] == data[0]
        assert objs[1][0] is f
        assert objs[1][1] == data[1]


def test_reader_split():
    with io.BytesIO(vals[0][:1]) as buf:
        with chunkpkl.Reader(buf) as f:
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
            assert objs[0][1] == data[0]
            assert objs[0][0] is f
            assert amt == buf.tell()

    with io.BytesIO(vals[0] + vals[1][:1]) as buf:
        with chunkpkl.Reader(buf) as f:
            objs = []
            amt = f.readinto(objs)
            assert amt > 0
            assert f.readinto(objs) < 0
            assert objs[0][0] is f
            assert objs[0][1] == data[0]

            cur = buf.tell()
            buf.write(vals[1][1:])
            buf.seek(cur)
            amt2 = f.readinto(objs)
            assert amt2 > 0
            assert f.readinto(objs) < 0
            assert objs[1][0] is f
            assert objs[1][1] == data[1]
            assert amt + amt2 == buf.tell()

def test_reader_multisplit():
    with io.BytesIO(vals[0][:1]) as buf:
        buf.write(vals[0])
        buf.write(vals[1][:1])
        buf.seek(0)
        with chunkpkl.Reader(buf) as f:
            objs = []
            amt = f.readinto1(objs)
            assert amt > 0
            assert f.readinto1(objs) < 0
            assert objs[0][0] is f
            assert objs[0][1] == data[0]

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
            assert objs[0][0] is f
            assert objs[0][1] == data[1]
            assert amt + amt2 == buf.tell()



def test_writer():
    buf = io.BytesIO()
    with chunkpkl.BWriter(buf) as f:
        data = b'hello'
        f.write(data)
        assert not f
        ser = buf.getvalue()
        assert struct.unpack_from('>BB', ser) == (0, len(pickle.dumps(data)))
        assert ser[2:] == pickle.dumps(data)


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

    with chunkpkl.QWriter(dummy(io.BytesIO())) as f:
        data = b'hello'
        f.write(data)
        assert f
        while f:
            assert f.flush1()

        ser = f.f.f.getvalue()
        assert struct.unpack_from('>BB', ser) == (0, len(pickle.dumps(data)))
        assert ser[2:] == pickle.dumps(data)


def test_readertime():
    setup = '\n'.join((
        'from jhsiao.ipc.formats.stream import chunkpkl',
        'import numpy as np',
        'import io',
        'buf = io.BytesIO()',
        'with chunkpkl.BWriter(buf) as w:',
        '    w.write(32)',
        '    w.write((1, 2, 3))',
        '    w.write(np.empty((480,640,3), np.uint8))',
        '    w.detach()',
        'f = chunkpkl.Reader(buf)',
    ))
    script = '\n'.join((
        'buf.seek(0)',
        'objs = []',
        'while f.readinto(objs) >= 0:',
        '    pass',
        ))
    print(min(timeit.repeat(script, setup, repeat=10, number=100)))

def make_test_split_readertime(char):
    def split_test():
        setup = '\n'.join((
            'from jhsiao.ipc.formats.stream import chunkpkl',
            'import pickle',
            'import numpy as np',
            'import io',
            'buf = io.BytesIO()',
            'with chunkpkl.BWriter(buf) as w:',
            '    w.write(32)',
            '    w.write((1, 2, 3))',
            '    w.write(np.full((480,640,3), ord({}), np.uint8))'.format(char),
            '    w.detach()',
            'import os',
            'r, w = os.pipe()',
            'r = io.open(r, "rb")',
            'w = io.open(w, "wb")',
            'view = memoryview(bytearray(1024))',
            'readercls = chunkpkl.Reader',
            ))

        script = '\n'.join((
            'buf.seek(0)',
            'objs = []',
            'with readercls(r) as f:',
            '    amt = buf.readinto(view)',
            '    while amt:',
            '        w.write(view[:amt])',
            '        w.flush()',
            '        f.readinto1(objs)',
            '        amt = buf.readinto(view)',
            '    while len(objs) != 3:',
            '        f.readinto1(objs)',
            '    f.detach()',
            ))
        print(min(timeit.repeat(script, setup, repeat=10, number=5)))
    return split_test

test_split_readertime_worst = make_test_split_readertime('pickle.STOP')
test_split_readertime_best = make_test_split_readertime('"a"')
