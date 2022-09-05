from setuptools import setup
from jhsiao.namespace import make_ns, fdir

make_ns('jhsiao', dir=fdir(__file__))
setup(
    name='jhsiao-ipc',
    version='0.0.1',
    author='Jason Hsiao',
    author_email='oaishnosaj@gmail.com',
    description='Interprocess communication (sockets, shared memory, etc)',
    packages=['jhsiao', 'jhsiao.ipc'],
)
