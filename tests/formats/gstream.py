import timeit

from jhsiao.ipc.formats.gstream import (
    gline,
    gchunk,
    gchunkpkl
)

def test_gchunk():
    import io
    import struct
    with io.BytesIO() as dummy:
        messages = [b'hello', b'world', b'hello world']
        for msg in messages:
            dummy.write(struct.pack('<Q', len(msg)))
            dummy.write(msg)
        out = []
        r = gchunk.GChunkReader(dummy, out)
        dummy.seek(0)
        it = r._iter()
        buf = next(it)
        while buf is not None:
            amt = dummy.readinto(buf[:3])
            if amt:
                buf = it.send(amt)
            else:
                break
        assert out == messages
        out = []
        dummy.seek(0)
        r = gchunk.GChunkReader(dummy, out, True, buffersize=9)
        result = r.read()
        while result is None or result >= 0:
            result = r.read()
        assert out == messages

        del out[:]
        dummy.seek(0)
        for result in r.readit():
            if result is not None and result < 0:
                break
        assert out == messages

        del out[:]
        dummy.seek(0)
        for result in gchunk.chunk_iter_tryread(dummy, out, False, buffersize=9):
            if result is not None and result < 0:
                break
        assert out == messages

        del out[:]
        dummy.seek(0)
        for result in gchunk.chunk_iter_yieldfrom(dummy, out, False, buffersize=9):
            if result is not None and result < 0:
                break
        assert out == messages

        del out[:]
        dummy.seek(0)
        for result in gchunk.chunk_iter_send(dummy, out, False, buffersize=9):
            if result is not None and result < 0:
                break
        assert out == messages

        del out[:]
        dummy.seek(0)
        for result in gchunk.chunk_iter_raw(dummy, out, False, buffersize=9):
            if result is not None and result < 0:
                break
        assert out == messages

        del out[:]
        dummy.seek(0)
        for result in gchunk.chunk_iter_cachedot(dummy, out, False, buffersize=9):
            if result is not None and result < 0:
                break
        assert out == messages



def test_gchunkpkl():
    import pickle
    import io
    import struct
    s = struct.Struct('<Q')
    with io.BytesIO() as dummy:
        messages = [(1,2), 3.14, 'hello world']
        for msg in messages:
            data = pickle.dumps(msg)
            dummy.write(s.pack(len(data)))
            dummy.write(data)
        dummy.seek(0)
        out = []
        r = gchunkpkl.GChunkPklReader(dummy, out, True, buffersize=s.size)
        result = r.read()
        while result is None or result >= 0:
            result = r.read()
        assert out == messages

        del out[:]
        dummy.seek(0)
        for result in r.readit():
            if result is not None and result < 0:
                break
        assert out == messages

def test_gline():
    import io
    with io.BytesIO() as dummy:
        messages = [b'hello\n', b'world\n', b'hello world\n', b'the end but no newline']
        dummy.writelines(messages)
        dummy.seek(0)
        out = []
        r = gline.line_iter(dummy, out, True, buffersize=3)
        while next(r) != -1:
            pass
        assert out == messages

def _run_timings(tests, setup, repeat, number):
    fmt = '{{:{}}}'.format(max(map(len, tests))).format
    for name, script in tests.items():
        print(
            fmt(name),
            min(timeit.repeat(script, setup, repeat=repeat, number=number)))


def test_timegchunk():
    setup = r'''import io
from jhsiao.ipc.formats.gstream import gchunk
from jhsiao.ipc.formats.stream import chunk
import struct
dummy = io.BytesIO()
dummy2 = io.BytesIO()
for msg in [b'hello', b'world', b'hello world']:
    dummy.write(struct.pack('<Q', len(msg)))
    dummy.write(msg)
    dummy2.write(struct.pack('>BQ', 3, len(msg)))
    dummy2.write(msg)

v = dummy.getvalue()
v2 = dummy2.getvalue()
for i in range(500):
    dummy.write(v)
    dummy2.write(v2)'''
    script1 = '''out = []
dummy.seek(0)
r = gchunk.GChunkReader(dummy, out, True)
result = r.read()
while result is None or result >= 0:
    result = r.read()
'''
    script2 = '''out = []
dummy.seek(0)
r = gchunk.GChunkReader(dummy, out, True)
for result in r.readit():
    if result is not None and result < 0:
        break'''
    script3 = '''out = []
dummy2.seek(0)
r = chunk.Reader(dummy2)
while r.readinto1(out) != -1:
    pass
r.detach()'''
    script4 = '''out = []
dummy.seek(0)
it = gchunk.chunk_iter_tryread(dummy, out, True)
while next(it) != -1:
    pass'''
    script5 = '''out = []
dummy.seek(0)
it = gchunk.chunk_iter_yieldfrom(dummy, out, True)
while next(it) != -1:
    pass'''
    script6 = '''out = []
dummy.seek(0)
it = gchunk.chunk_iter_send(dummy, out, True)
while next(it) != -1:
    pass'''
    script7 = '''out = []
dummy.seek(0)
it = gchunk.chunk_iter_raw(dummy, out, True)
while next(it) != -1:
    pass'''
    script8 = '''out = []
dummy.seek(0)
it = gchunk.chunk_iter_cachedot(dummy, out, True)
while next(it) != -1:
    pass'''
    _run_timings(
        dict(
            clsread=script1,
            readit=script2,
            readinto1=script3,
            tryread=script4,
            yieldfrom=script5,
            send=script6,
            raw=script7,
            cachedot=script8,
            ),
        setup, 10, 500)

def test_timegline():
    setup = r'''import io
from jhsiao.ipc.formats.gstream import gline
from jhsiao.ipc.formats.stream import line
dummy = io.BytesIO()
messages = [b'hello\n', b'world\n', b'hello world\n', b'the end but no newline\n'] * 1000
dummy.writelines(messages)'''
    script1 = '''out = []
dummy.seek(0)
reader = gline.line_iter(dummy, out, True)
for result in reader:
    if result == -1:
        break
'''
    script2 = '''out = []
dummy.seek(0)
reader = gline.GLineReader(dummy, out, True)
for result in reader.readit():
    if result == -1:
        break
'''

    script4 = '''out = []
dummy.seek(0)
reader = line.Reader(dummy)
while reader.readinto1(out) != -1:
    pass
reader.detach()
'''
    _run_timings(
        dict(rawiter=script1, senditer=script2, readinto1=script4),
        setup, 10, 100
    )
