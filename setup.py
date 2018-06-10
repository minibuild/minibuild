from setuptools import setup
from codecs import open
import os.path
import sys


here = os.path.abspath(os.path.dirname(__file__))
about = {}

if 'sdist' in sys.argv:
    import pypandoc
    long_description = pypandoc.convert(os.path.join(here, 'README.md'), 'rst')
else:
    with open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
        long_description = f.read()


with open(os.path.join(here, 'minibuild', '__version__.py'), 'r', 'utf-8') as f:
    exec(f.read(), about)

setup(
    name = 'minibuild',
    packages=['minibuild'],
    package_data={'': ['LICENSE.txt']},
    version = about['__version__'],
    description = 'Build system aimed to be a pure Python alternative to GNU Make with builtin support of MSVS, GCC, clang',
    long_description=long_description,
    long_description_content_type='text/x-rst',
    author = 'Vitaly Murashev',
    author_email = 'vitaly.murashev@gmail.com',
    license = 'MIT',
    url = 'https://minibuild.github.io/minibuild/',
    download_url = 'https://github.com/minibuild/minibuild/archive/%s.tar.gz' % about['__version__'],
    keywords = 'buildsystem build',
    python_requires=">=2.7",
    classifiers = [
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'License :: OSI Approved :: MIT License',
        'Operating System :: POSIX :: Linux',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: Microsoft :: Windows',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: Implementation :: CPython',
        'Topic :: Software Development :: Build Tools',
    ],
    project_urls = {
        'Source': 'https://github.com/minibuild/minibuild/',
    },
    platforms = ['Linux', 'Windows', 'MacOSX'],
    zip_safe = True
)
