from setuptools import setup
from jhsiao.namespace import make_ns

make_ns('jhsiao')
setup(
    name='jhsiao-ipc',
    version='0.0.1',
    author='Jason Hsiao',
    author_email='oaishnosaj@gmail.com',
    description='Interprocess communication (sockets, shared memory, etc)',
    packages=['jhsiao', 'jhsiao.ipc'],
)
