"""benchmark various generator usage patterns


1. just call next, everything handled inside the generator.
2. yield a buffer to read into. when task is done, then send()
   the result.
"""
from jhsiao.tests import bench

p = bench.parser()
p.add_argument('--resources', type=int, default=10)
p.add_argument('--readchunk', type=int, default=493)
p.add_argument('--target', type=int, default=3456)
p.add_argument('--total', type=int, default=8192*5)
args = p.parse_args()

setup = '''
class Dummy(object):
    def __init__(self):
        self.total = {total}

    def readinto(self, buf):
        if self.total < {readchunk}:
            self.total = 0
            return self.total
        else:
            self.total -= {readchunk}
            return {readchunk}

def internal2(idx, rm, f, target={target}):
    buf = memoryview(bytearray(8192))
    readinto = f.readinto
    total = 0
    while 1:
        while total < target:
            amt = readinto(buf)
            if not amt:
                rm.add(idx)
                yield
                return
            total += amt
            yield
        total -= target


def internal(f, target={target}):
    buf = memoryview(bytearray(8192))
    readinto = f.readinto
    total = 0
    while 1:
        while total < target:
            amt = readinto(buf)
            if not amt:
                return
            total += amt
            yield
        total -= target

def external(f, target={target}):
    buf = memoryview(bytearray(8192))
    readinto = f.readinto
    total = 0
    while 1:
        total = yield [readinto, buf, total, target]
        if total < target:
            return
        total -= target
'''

internal = '''
gens = {{
    i: [i, internal(Dummy())]
    for i in range({resources})}}
toremove = set()
while gens:
    for idx, gen in gens.values():
        try:
            next(gen)
        except StopIteration:
            toremove.add(idx)
    if toremove:
        for idx in toremove:
            gens.pop(idx)
        toremove.clear()
'''.format(resources=args.resources)

internal2 = '''
toremove = set()
gens = {{
    i: [i, internal2(i, toremove, Dummy())]
    for i in range({resources})}}
while gens:
    for idx, gen in gens.values():
        next(gen)
    if toremove:
        for idx in toremove:
            gens.pop(idx)
        toremove.clear()
'''.format(resources=args.resources)


external = '''
gens = {{
    i: [i, external(Dummy()), None]
    for i in range({resources})}}
toremove = set()

for item in gens.values():
    item[2] = next(item[1])

while gens:
    for item in gens.values():
        idx, gen, job = item
        readinto, buf, total, target = job
        amt = readinto(buf)
        if amt == 0:
            toremove.add(idx)
        total += amt
        if total >= target:
            item[2] = gen.send(total)
    if toremove:
        for idx in toremove:
            gens.pop(idx)
        toremove.clear()
'''.format(resources=args.resources)

bench.run(
    title='generators',
    setup=setup.format(
        resources=args.resources,
        readchunk=args.readchunk,
        target=args.target,
        total=args.total,
    ),
    external=external,
    internal=internal,
    internal2=internal2,
    args=args,
)
