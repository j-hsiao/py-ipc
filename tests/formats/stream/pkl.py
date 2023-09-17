from jhsiao.ipc.formats.stream import pkl
import io
import os
import numpy as np
import time
import timeit
import pickle

def test_reader():
    r, w = os.pipe()
    reader = io.open(r, 'rb')
    writer = io.open(w, 'wb')
    pr = pkl.Reader(reader)
    objs = []
    item1 = memoryview(pickle.dumps(b'hello world'))
    arr = np.empty((480,640,3), np.uint8)
    item2 = memoryview(pickle.dumps(arr))
    try:
        writer.write(item1[:1])
        writer.flush()
        assert pr.readinto1(objs) == 0

        writer.write(item1[1:])
        writer.flush()
        assert pr.readinto1(objs) > 0

        writer.write(item1)
        writer.flush()
        objs, ret = pr.read()
        assert len(objs) == 1
        assert ret > 0

        blocksize = 1024
        for stop in range(blocksize, len(item2) + blocksize - 1, blocksize):
            writer.write(item2[stop-blocksize:stop])
            writer.flush()
            if stop < len(item2):
                assert pr.readinto1(objs) == 0
            else:
                assert pr.readinto1(objs) > 1
        assert np.all(arr == objs[-1])
        t1 = time.time()
        for stop in range(blocksize, len(item2) + blocksize - 1, blocksize):
            writer.write(item2[stop-blocksize:stop])
            writer.flush()
            if stop < len(item2):
                assert pr.readinto1(objs) == 0
            else:
                assert pr.readinto1(objs) > 1
        assert np.all(arr == objs[-1])
        t2 = time.time()
        print(t2-t1)

        writer.close()
        assert pr.readinto1(objs) == -1

        print(len(pr.buf), len(item2))
        print('pass')
    finally:
        pr.close()
        writer.close()

def test_readertime():
    setup = '\n'.join((
        'from jhsiao.ipc.formats.stream import pkl',
        'import numpy as np',
        'import io',
        'buf = io.BytesIO()',
        'import pickle',
        'pickle.dump(32, buf)',
        'pickle.dump((1, 2, 3), buf)',
        'pickle.dump(np.empty((480,640,3), np.uint8), buf)',
        'f = pkl.Reader(buf)'
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
            'from jhsiao.ipc.formats.stream import pkl',
            'import numpy as np',
            'import io',
            'buf = io.BytesIO()',
            'import pickle',
            'pickle.dump(32, buf)',
            'pickle.dump((1, 2, 3), buf)',
            'pickle.dump(np.full((480,640,3), ord({}), np.uint8), buf)'.format(char),
            'import os',
            'r, w = os.pipe()',
            'r = io.open(r, "rb")',
            'w = io.open(w, "wb")',
            'view = memoryview(bytearray(1024))',
            'readercls = pkl.Reader',
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



def test_writer():
    class Dummy(object):
        def __init__(self, chunk):
            self.chunk = chunk
            self.total = 0

        def write(self, data):
            amt = min(self.chunk, len(data))
            self.total += amt
            return amt

        def flush(self):
            pass

        def close(self):
            pass

    chunksize = 512
    w = Dummy(chunksize)

    data = bytearray(480*640*3)
    total = len(pickle.dumps(data))
    with pkl.QWriter(w) as qw:
        qw.write(data)
        while w.total < total:
            assert qw
            assert qw.flush1() <= chunksize
        assert not qw

    with pkl.QWriter(io.BytesIO()) as qw:
        qw.write(data)
        assert qw.flush()
        qw.f.seek(0)
        assert pickle.load(qw.f) == data
