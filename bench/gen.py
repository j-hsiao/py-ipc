"""benchmark various generator usage patterns

All methods should:
1. read some data
2. if enough, process the data
3. yield

naming:
    outer: handled in the run loop
    inner: handled in a generator
    sub  : handled in a generator within the generator
    func_xxx : handled in a func called by xxx



1. just call next, everything handled inside the generator.
2. yield a buffer to read into. when task is done, then send()
   the result.
------------------------------
results
------------------------------
i5-8265u @ 1.60GHz

1 read per message
$ py bench/gen.py --readchunk 512 --target 512 --total $((8192*1000)) -n 1
----------
generators
All results match!
                                                      :   min    mean     max
           read_inner_processing_inner_NoStopIteration: 0.13774 0.14070 0.14706
             read_inner_processing_inner_StopIteration: 0.13919 0.14426 0.15308
                             read_inner_processing_sub: 0.16523 0.16638 0.17037
                      read_inner_processing_func_inner: 0.16748 0.17176 0.17814
      read_outer_processing_inner_readjob_merge_assign: 0.17212 0.17505 0.17894
            read_outer_processing_inner_readjob_assign: 0.17471 0.17743 0.18280
                read_sub_processing_inner_ReuseReadSub: 0.17697 0.19012 0.22882
read_outer_processing_func_outer_readjob_assign_merged: 0.17972 0.18622 0.19704
           read_outer_processing_inner_readjob_replace: 0.18700 0.19071 0.19891
         read_outer_processing_inner_readjob_sepassign: 0.18774 0.22385 0.38730
                      read_sub_processing_inner_nosend: 0.22436 0.24038 0.27034
                             read_sub_processing_inner: 0.23172 0.24392 0.26157
       read_outer_processing_inner_readjob_sliceassign: 0.23641 0.30004 0.48568

multiple reads per message
$ py bench/gen.py --readchunk 512 --target 2048 --total $((8192*1000)) -n 1
----------
generators
All results match!
                                                      :   min    mean     max
             read_inner_processing_inner_StopIteration: 0.13813 0.14941 0.17836
           read_inner_processing_inner_NoStopIteration: 0.14270 0.14679 0.15003
      read_outer_processing_inner_readjob_merge_assign: 0.14371 0.14613 0.14959
           read_outer_processing_inner_readjob_replace: 0.14526 0.14948 0.15326
         read_outer_processing_inner_readjob_sepassign: 0.14528 0.14894 0.15394
read_outer_processing_func_outer_readjob_assign_merged: 0.14530 0.14616 0.14757
            read_outer_processing_inner_readjob_assign: 0.14641 0.15068 0.15729
                      read_inner_processing_func_inner: 0.14818 0.15420 0.15894
       read_outer_processing_inner_readjob_sliceassign: 0.14899 0.15156 0.15975
                             read_inner_processing_sub: 0.14918 0.15335 0.16019
                      read_sub_processing_inner_nosend: 0.15986 0.16323 0.16949
                read_sub_processing_inner_ReuseReadSub: 0.16042 0.16835 0.17537
                             read_sub_processing_inner: 0.16465 0.16869 0.17425

multiple messages per read
$ py bench/gen.py --readchunk 512 --target 128 --total $((8192*1000)) -n 1
----------
generators
All results match!
                                                      :   min    mean     max
           read_inner_processing_inner_NoStopIteration: 0.19253 0.19967 0.20300
             read_inner_processing_inner_StopIteration: 0.19501 0.20039 0.20359
                             read_inner_processing_sub: 0.21567 0.22423 0.23035
                      read_inner_processing_func_inner: 0.22068 0.23179 0.24482
            read_outer_processing_inner_readjob_assign: 0.22538 0.23216 0.23654
      read_outer_processing_inner_readjob_merge_assign: 0.22604 0.23033 0.23463
                read_sub_processing_inner_ReuseReadSub: 0.22669 0.23252 0.24473
read_outer_processing_func_outer_readjob_assign_merged: 0.22881 0.23701 0.24166
         read_outer_processing_inner_readjob_sepassign: 0.23280 0.24041 0.25449
           read_outer_processing_inner_readjob_replace: 0.23364 0.23898 0.24653
                      read_sub_processing_inner_nosend: 0.23587 0.24284 0.25107
       read_outer_processing_inner_readjob_sliceassign: 0.24174 0.24535 0.25333
                             read_sub_processing_inner: 0.24802 0.25326 0.26084


Focusing more on long-running connections, read and processing in a
single generator always performs best in all cases.  For read:message
ratio <= 1, read_inner_processing_sub is generally, good.  However, when
ratio >= 1, read_inner_processing_sub drops fairly low On the other
hand, across all test cases, read_outer_processing_inner seems to
perform fairly consistently.  The relative performance difference is
fairly consistent, the faster method is about 4% faster on this machine.
In the case of multiple reads per message, if the server is very busy,
being overwhelmed, the data will probably be buffered anyways which
means the read/message ratio will eventually drop towards 1 or below.
Since read_inner_processing_sub performs better in this case, plus, due
to the ease of implementation, it will be the chosen method.

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

class GenBase(Base):
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

class TEST_read_inner_processing_inner_NoStopIteration(GenBase):
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
            while 1:
                amt = readinto(buf[total:])
                if amt:
                    total += amt
                    if total < target:
                        yield
                    else:
                        break
                else:
                    self.rm.add(idx)
                    yield
            while total >= target:
                total -= target
                result[idx] += 1

class TEST_read_inner_processing_inner_StopIteration(Base):
    """Generator ends so StopIteration must be caught."""
    def gen(self, idx, f):
        result = self.result
        target = self.args.target
        buf = memoryview(bytearray(8192))
        readinto = f.readinto
        total = 0
        while 1:
            while 1:
                amt = readinto(buf[total:])
                if amt:
                    total += amt
                    if total < target:
                        yield
                    else:
                        break
                else:
                    return
            while total >= target:
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

class TEST_read_inner_processing_func_inner(GenBase):
    """Use a generator for reading.

    Instead of processing generator calling reading generator,
    have the reading generator call the processing generator
    instead.
    """
    def gen(self, idx, f):
        process = self.process
        readinto = f.readinto
        buf = memoryview(bytearray(8192))
        total = 0
        target = self.args.target
        result = self.result
        while 1:
            while 1:
                amt = readinto(buf[total:])
                if amt:
                    total += amt
                    if total < target:
                        yield
                    else:
                        break
                else:
                    self.rm.add(idx)
                    yield
            buf, total, target = process(buf, total, target, idx, result)

    def process(self, buf, total, target, idx, result):
        while total >= target:
            total -= target
            result[idx] += 1
        return buf, total, target


class TEST_read_inner_processing_sub(GenBase):
    """Use a generator for reading.

    Instead of processing generator calling reading generator,
    have the reading generator call the processing generator
    instead.
    """
    def gen(self, idx, f):
        processor = self.process(idx)
        readinto = f.readinto
        buf, total, target = next(processor)
        while 1:
            while 1:
                amt = readinto(buf[total:])
                if amt:
                    total += amt
                    if total < target:
                        yield
                    else:
                        break
                else:
                    self.rm.add(idx)
                    yield
            buf, total, target = processor.send(total)

    def process(self, idx):
        buf = memoryview(bytearray(8192))
        target = self.args.target
        result = self.result
        total = 0
        while 1:
            total = yield buf, total, target
            while total >= target:
                total -= target
                result[idx] += 1


class TEST_read_sub_processing_inner(GenBase):
    """Reading is handled via sub-generator internally.

    To avoid rewriting the reading logic, put it in a generator.
    """
    @staticmethod
    def readbufs(readinto, buf, total, target):
        while 1:
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
                    elif total < 0:
                        rm.add(idx)
                        yield
                    else:
                        break
            total -= target
            result[idx] += 1

class TEST_read_sub_processing_inner_ReuseReadSub(GenBase):
    """Reading is handled via sub-generator internally.

    To avoid rewriting the reading logic, put it in a generator.
    """
    @staticmethod
    def readbufs():
        total = None
        while 1:
            readinto, buf, total, target = yield total
            while 1:
                amt = readinto(buf[total:])
                if amt:
                    total += amt
                    if total >= target:
                        break
                    yield
                else:
                    yield -1

    def gen(self, idx, f):
        result = self.result
        target = self.args.target
        buf = memoryview(bytearray(8192))
        readinto = f.readinto
        total = 0
        rm = self.rm
        readbufs = self.readbufs()
        next(readbufs)
        while 1:
            if total < target:
                total = readbufs.send([readinto, buf, total, target])
                while total is None:
                    yield
                    total = next(readbufs)
                if total < 0:
                    rm.add(idx)
                    yield
            total -= target
            result[idx] += 1


class TEST_read_sub_processing_inner_nosend(GenBase):
    """Reading is handled via sub-generator internally.

    To avoid rewriting the reading logic, put it in a generator.
    """
    @staticmethod
    def readbufs(readinto, buf, total, target, out):
        while 1:
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


class TEST_read_outer_processing_inner_readjob_replace(Base):
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

class TEST_read_outer_processing_func_outer_readjob_assign_merged(Base):
    """Test not using a generator.  Instead use a function.

    State would need to be stored (list? closure?)
    to track processing "state", a "next function" could be
    stored.
    """
    def __init__(self, args):
        self.result = [0] * args.resources
        self.args = args
        self.rm = set()
        self.jobs = {
            i: self.state(i, self.dummy())
            for i in range(args.resources)
        }

    def state(self, idx, resource):
        """Return a state struct."""
        return [idx, resource.readinto, memoryview(bytearray(8192)), 0, self.args.target]

    def process(self, idx, state, result, buf, tot, tgt):
        while tot >= tgt:
            tot -= tgt
            result[idx] += 1
        state[3] = tot

    def run(self):
        jobs = self.jobs
        rm = self.rm
        result = self.result
        process = self.process
        while jobs:
            for state in jobs.values():
                idx, func, buf, tot, tgt = state
                amt = func(buf[tot:])
                if amt:
                    tot += amt
                    if tot >= tgt:
                        process(idx, state, result, buf, tot, tgt)
                    else:
                        state[3] = tot
                else:
                    rm.add(idx)
            if rm:
                for idx in rm:
                    jobs.pop(idx)
                rm.clear()


class TEST_read_outer_processing_inner_readjob_assign(Base):
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


class TEST_read_outer_processing_inner_readjob_merge_assign(Base):

    def gen(self, idx, f):
        result = self.result
        target = self.args.target
        buf = memoryview(bytearray(8192))
        readinto = f.readinto
        item = self.gens[idx]
        item.extend([readinto, buf, 0, target])
        while 1:
            total = yield
            while total >= target:
                total -= target
                result[idx] += 1
            item[4] = total

    def run(self):
        gens = self.gens
        for g in gens.values():
            next(g[1])
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

class TEST_read_outer_processing_inner_readjob_sliceassign(
    TEST_read_outer_processing_inner_readjob_merge_assign):
    """Modify job list instead of reassign to dict.

    simulate fully changing the job.
    """
    def gen(self, idx, f):
        result = self.result
        target = self.args.target
        buf = memoryview(bytearray(8192))
        readinto = f.readinto
        item = self.gens[idx]
        item.extend([readinto, buf, 0, target])
        while 1:
            total = yield
            while total >= target:
                total -= target
                result[idx] += 1
            item[3:6] = buf, total, target

class TEST_read_outer_processing_inner_readjob_sepassign(
    TEST_read_outer_processing_inner_readjob_merge_assign):
    """Modify job list instead of reassign to dict.

    simulate fully changing the job.
    """
    def gen(self, idx, f):
        result = self.result
        target = self.args.target
        buf = memoryview(bytearray(8192))
        readinto = f.readinto
        item = self.gens[idx]
        item.extend([readinto, buf, 0, target])
        while 1:
            total = yield
            while total >= target:
                total -= target
                result[idx] += 1
            item[3] = buf
            item[4] = total
            item[5] = target


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
