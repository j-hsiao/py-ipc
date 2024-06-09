from jhsiao.tests import bench
import sys

setup = '''

from jhsiao.ipc.polling.gen import prelen

RHEAD = prelen.RHEAD
WHEAD = prelen.WHEAD
length = {}
WHEADS = [None]*65

for thing in WHEAD[::-1]:
    for i in range((thing[0].size*8)+1):
        WHEADS[i] = thing

vlen = memoryview(bytearray(9))
if length < 0x3f:
    vlen[0] = length
    vlen = vlen[:1]
else:
    for (fmt, mx, code) in WHEAD:
        if length <= mx:
            vlen[0] = code
            fmt.pack_into(vlen, 1, length)
            vlen = vlen[:1+fmt.size]
            break

fixed = WHEAD[-1][0]
flen = memoryview(bytearray(fixed.pack(length)))
'''

p = bench.parser()
p.add_argument('--length', '-l', default=1)
p.add_argument('--fixed', '-f', action='store_true')
args = p.parse_args()
try:
    args.length = int(args.length)
except ValueError:
    args.length = int(args.length, 16)


tests = dict(
    loop='''
buf = memoryview(bytearray(9))
if length <= 0x3f:
    buf[0] = length
    result = buf[:1]
else:
    for fmt, mx, code in WHEAD:
        if length <= mx:
            buf[0] = code
            fmt.pack_into(buf, 1, length)
            result = buf[:fmt.size+1]
            break
''',
    idx='''
buf = memoryview(bytearray(9))
if length <= 0x3f:
    buf[0] = length
    result = buf[:1]
else:
    fmt, _, code = WHEADS[length.bit_length()]
    buf[0] = code
    fmt.pack_into(buf, 1, length)
    result = buf[:1+fmt.size]
''',
)
if args.fixed:
    tests.update(dict(
        fixed='result = memoryview(fixed.pack(length))'
))
else:
    tests.update(dict(
        eq=(lambda a,b: a.tobytes() == b.tobytes()),
))

bench.run(
    title='write',
    setup=setup.format(args.length),
    args=args,
    **tests
)

bench.run(
    title='read',
    setup=setup.format(args.length),
    eq=bench.eq,
    args=args,
    ifs='''
code = vlen[0]
if code <= 0x3f:
    result = vlen[0]
else:
    if code == 0x40:
        result = RHEAD[1].unpack_from(vlen, 1)[0]
    elif code == 0x80:
        result = RHEAD[2].unpack_from(vlen, 1)[0]
    elif code == 0xC0:
        result = RHEAD[3].unpack_from(vlen, 1)[0]
''',
    div='''
code = vlen[0]
if code <= 0x3f:
    result = vlen[0]
else:
    result = RHEAD[code // 0x40].unpack_from(vlen, 1)[0]
''',
    fixed='result = fixed.unpack(flen)[0]',
)
