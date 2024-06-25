"""benchmark various generator usage patterns


1. just call next, everything handled inside the generator.
2. yield a buffer to read into. when task is done, then send()
   the result.
------------------------------
results
------------------------------

many reads per message:
    $ py bench/gen.py --readchunk 32 --target 129 --total $((8192*10))
    ----------
    generators
    All results match!
                                  :   min    mean     max
                     external_read: 1.55549 1.61607 1.82584
           external_read_mergeitem: 1.47315 1.51084 1.54783
              external_read_modjob: 1.49734 1.54717 1.67252
    external_read_modjob_fullslice: 1.74045 1.78553 1.90923
    external_read_modjob_sepassign: 1.78536 1.86778 2.13546
               internal_no_stop_it: 1.84695 1.88516 1.96014
                      internal_ret: 1.83916 1.87835 2.05013
              internal_subgen_read: 2.19093 2.28064 2.63903
      internal_subgen_read_nocheck: 2.16088 2.25993 2.54376

many messages per read
    $ py bench/gen.py --readchunk 129 --target 32 --total $((8192*10))
    ----------
    generators
    All results match!
                                  :   min    mean     max
                     external_read: 0.81203 0.87117 0.95545
           external_read_mergeitem: 0.77139 0.80076 0.83983
              external_read_modjob: 0.77356 0.79058 0.80179
    external_read_modjob_fullslice: 0.84676 0.93543 1.12242
    external_read_modjob_sepassign: 0.80243 0.84309 0.99546

               internal_no_stop_it: 0.72549 0.73555 0.75236
                      internal_ret: 0.73130 0.74083 0.75210

              internal_subgen_read: 1.13784 1.16177 1.17880
      internal_subgen_read_nocheck: 1.14287 1.18182 1.27537



method summary:
    Handle reading external to generator:
        This is the best choice if there will be many reads per message
            1. very large messages
            2. slow network (limited by network not performance...)
        Reading code is re-used
    Handle reading internal to generator:
        This is the fastest choice if there are many messages per read
            1. messages are very small and sent with high frequency
        Reading code is NOT re-used. The generators are much more of a
        hassle to write/maintain.
    Handle reading in an extra generator.
        This has the worst performance.  It allows reusing reading code.
        probably never choose this one...

rationalization?
    Subgenerator methods have worst performance and has no benefit over
    any of the other implementation methods.  It will not be analyzed...

    external:
        add a "job"
        Each iteration, unpack the "job", and read a little.
        If ready, next(generator): new job, handle data, etc
        Otherwise, update job
    internal:
        each iteration: next(generator)
            read a little
            handle data if ready...

    In the many reads per message situation, the majority of time
    is spent in the [unpack job, read, update job] portion (external)
    and [next(generator), read] (internal).
    Calling the generator is probably more expensive than unpack/update
    job. so in this situation, external reading is faster.

    In the many messages per job situation, external reading has to do
    everything internal reading does, but also update the job list.
    It makes sense that it would be slower than internal reading from
    this perspective.




    In this case, external reading has the extra step of unpacking
    the read arguments and re-assigning the new read arguments every
    single iteration.  Because external reading also allows reusing
    the reading code, it is probably the best choice.
"""
from jhsiao.tests import bench

class Dummy(object):
    """Dummy reader."""
    def __init__(self, args):
        self.total = args.total
        self.chunksize = args.readchunk

    def readinto(self, buf):
        amt = min(len(buf), self.chunksize)
        if self.total < amt:
            try:
                return self.total
            finally:
                self.total = 0
        else:
            self.total -= amt
            return amt

class Base(object):
    def __init__(self, args):
        self.result = [0] * args.resources
        self.args = args
        self.rm = set()
        self.gens = {
            i: [i, self.gen(i, self.dummy())]
            for i in range(args.resources)}

    def __call__(self):
        self.run()
        return self.result

    def dummy(self):
        return Dummy(self.args)

class TEST_internal_no_stop_it(Base):
    """Generator stops by adding idx to rm.

    reading is handled internally.
    """
    def gen(self, idx, f):
        result = self.result
        target = self.args.target
        buf = memoryview(bytearray(8192))
        readinto = f.readinto
        total = 0
        while 1:
            while total < target:
                amt = readinto(buf[total:])
                if not amt:
                    self.rm.add(idx)
                    yield
                    while 1:
                        self.rm.add(idx)
                        yield
                total += amt
                yield
            total -= target
            result[idx] += 1

    def run(self):
        gens = self.gens
        rm = self.rm
        while gens:
            for idx, gen in gens.values():
                next(gen)
            if rm:
                for idx in rm:
                    gens.pop(idx)
                rm.clear()

class TEST_internal_ret(Base):
    """Generator ends so StopIteration must be caught."""
    def gen(self, idx, f):
        result = self.result
        target = self.args.target
        buf = memoryview(bytearray(8192))
        readinto = f.readinto
        total = 0
        while 1:
            while total < target:
                amt = readinto(buf[total:])
                if not amt:
                    return
                total += amt
                yield
            total -= target
            result[idx] += 1

    def run(self):
        gens = self.gens
        rm = self.rm
        while gens:
            for idx, gen in gens.values():
                try:
                    next(gen)
                except StopIteration:
                    rm.add(idx)
            if rm:
                for idx in rm:
                    gens.pop(idx)
                rm.clear()
        return self.result

class TEST_internal_subgen_read(Base):
    """Reading is handled via sub-generator internally.

    To avoid rewriting the reading logic, put it in a generator.
    """
    @staticmethod
    def readbufs(readinto, buf, total, target):
        while total < target:
            amt = readinto(buf[total:])
            if amt:
                total += amt
                if total >= target:
                    yield total
                    return
                yield
            else:
                yield -1
                return

    def gen(self, idx, f):
        result = self.result
        target = self.args.target
        buf = memoryview(bytearray(8192))
        readinto = f.readinto
        total = 0
        rm = self.rm
        readbufs = self.readbufs
        while 1:
            if total < target:
                for total in readbufs(readinto, buf, total, target):
                    if total is None:
                        yield
                if total < 0:
                    rm.add(idx)
                    yield
                    return
            total -= target
            result[idx] += 1
            yield

    def run(self):
        gens = self.gens
        rm = self.rm
        while gens:
            for idx, gen in gens.values():
                try:
                    next(gen)
                except StopIteration:
                    rm.add(idx)
            if rm:
                for idx in rm:
                    gens.pop(idx)
                rm.clear()
        return self.result

class TEST_internal_subgen_read_nocheck(Base):
    """Reading is handled via sub-generator internally.

    To avoid rewriting the reading logic, put it in a generator.
    """
    @staticmethod
    def readbufs(readinto, buf, total, target, out):
        while total < target:
            amt = readinto(buf[total:])
            if amt:
                total += amt
                if total >= target:
                    out[0] = total
                    return
                yield
            else:
                out[0] = -1
                return

    def gen(self, idx, f):
        result = self.result
        target = self.args.target
        buf = memoryview(bytearray(8192))
        readinto = f.readinto
        total = 0
        rm = self.rm
        readbufs = self.readbufs
        readsult = [0]
        while 1:
            if total < target:
                yield from readbufs(readinto, buf, total, target, readsult)
                total = readsult[0]
                if total < 0:
                    rm.add(idx)
                    yield
                    return
            total -= target
            result[idx] += 1
            yield

    def run(self):
        gens = self.gens
        rm = self.rm
        while gens:
            for idx, gen in gens.values():
                try:
                    next(gen)
                except StopIteration:
                    rm.add(idx)
            if rm:
                for idx in rm:
                    gens.pop(idx)
                rm.clear()
        return self.result




class TEST_external_read(Base):
    """Leave the actual reading outside the handling generator.

    The reading part and error handling for the read specifically
    is the same regardless of formats.  Would be nice to not have to
    rewrite it over and over...
    method 1 = put it in the event loop.
    """
    def gen(self, idx, f):
        result = self.result
        target = self.args.target
        buf = memoryview(bytearray(8192))
        readinto = f.readinto
        total = 0
        while 1:
            total = yield [readinto, buf, total, target]
            while total >= target:
                total -= target
                result[idx] += 1

    def run(self):
        gens = {
            i: [i, g, next(g)]
            for i, g in self.gens.values()
        }
        rm = self.rm
        while gens:
            for item in gens.values():
                idx, gen, job = item
                readinto, buf, tot, tgt = job
                amt = readinto(buf[tot:])
                tot += amt
                if tot >= tgt:
                    item[2] = gen.send(tot)
                elif amt:
                    job[2] = tot
                else:
                    rm.add(idx)
            if rm:
                for idx in rm:
                    gens.pop(idx)
                rm.clear()

class TODO_TEST_external_read_func(Base):
    """Test not using a generator.  Instead use a function.

    State would need to be stored (list? closure?)
    to track processing "state", a "next function" could be
    stored.
    """
    # TODO

class TEST_external_read_modjob(Base):
    """Modify job list instead of reassign to dict."""
    def __init__(self, args):
        self.result = [0] * args.resources
        self.args = args
        self.rm = set()
        self.gens = {}
        for i in range(args.resources):
            g = self.gen(i, self.dummy())
            self.gens[i] = [i, g, next(g)]

    def gen(self, idx, f):
        result = self.result
        target = self.args.target
        buf = memoryview(bytearray(8192))
        readinto = f.readinto
        job = [readinto, buf, 0, target]
        total = yield job
        while 1:
            while total >= target:
                total -= target
                result[idx] += 1
            job[2] = total
            total = yield

    def run(self):
        gens = self.gens
        rm = self.rm
        while gens:
            for idx, gen, job in gens.values():
                func, buf, tot, tgt = job
                amt = func(buf[tot:])
                tot += amt
                if tot >= tgt:
                    gen.send(tot)
                elif amt:
                    job[2] = tot
                else:
                    rm.add(idx)
            if rm:
                for idx in rm:
                    gens.pop(idx)
                rm.clear()


class TEST_external_read_mergeitem(Base):
    def __init__(self, args):
        self.result = [0] * args.resources
        self.args = args
        self.rm = set()
        self.gens = {}
        for i in range(args.resources):
            item = [i]
            g = self.gen(i, self.dummy(), item)
            item.append(g)
            next(g)
            self.gens[i] = item

    def gen(self, idx, f, item):
        result = self.result
        target = self.args.target
        buf = memoryview(bytearray(8192))
        readinto = f.readinto
        item.extend([readinto, buf, 0, target])
        while 1:
            total = yield
            while total >= target:
                total -= target
                result[idx] += 1
            item[4] = total

    def run(self):
        gens = self.gens
        rm = self.rm
        while gens:
            for item in gens.values():
                idx, gen, readinto, buf, tot, tgt = item
                amt = readinto(buf[tot:])
                tot += amt
                if tot >= tgt:
                    gen.send(tot)
                elif amt:
                    item[4] = tot
                else:
                    rm.add(idx)
            if rm:
                for idx in rm:
                    gens.pop(idx)
                rm.clear()

class TEST_external_read_modjob_fullslice(TEST_external_read_modjob):
    """Modify job list instead of reassign to dict.

    simulate fully changing the job.
    """
    def gen(self, idx, f):
        result = self.result
        target = self.args.target
        buf = memoryview(bytearray(8192))
        readinto = f.readinto
        job = [readinto, buf, 0, target]
        total = yield job
        while 1:
            while total >= target:
                total -= target
                result[idx] += 1
            job[1:4] = buf, total, target
            total = yield

class TEST_external_read_modjob_sepassign(TEST_external_read_modjob):
    """Modify job list instead of reassign to dict.

    simulate fully changing the job.
    """
    def gen(self, idx, f):
        result = self.result
        target = self.args.target
        buf = memoryview(bytearray(8192))
        readinto = f.readinto
        job = [readinto, buf, 0, target]
        total = yield job
        while 1:
            while total >= target:
                total -= target
                result[idx] += 1
            job[1] = buf
            job[2] = total
            job[3] = target
            total = yield


p = bench.parser()
p.add_argument('--resources', type=int, default=10)
p.add_argument('--readchunk', type=int, default=493)
p.add_argument('--target', type=int, default=3456)
p.add_argument('--total', type=int, default=8192*5)
args = p.parse_args()

setup = '''
from __main__ import {items}, args
'''.format(items=', '.join([k for k in globals() if k.startswith('TEST_')]))

tests = {
    k.split('_', 1)[1]: 'result = {}(args)()'.format(k) for k in sorted(globals())
    if k.startswith('TEST_')
}

bench.run(
    title='generators',
    setup=setup.format(
        resources=args.resources,
        readchunk=args.readchunk,
        target=args.target,
        total=args.total,
    ),
    **tests,
    args=args,
    eq=bench.eq,
)
