from setuptools import setup, find_packages
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))
version = '0.8.1'

with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name = 'minibuild',
    packages=find_packages(exclude=['contrib', 'docs']),
    version = version,
    description = 'MiniBuild build system',
    long_description=long_description,
    author = 'Vitaly Murashev',
    author_email = 'vitaly.murashev@gmail.com',
    license = 'MIT',
    url = 'https://minibuild.github.io/minibuild/',
    download_url = 'https://github.com/minibuild/minibuild/archive/%s.tar.gz' % version,
    keywords = 'buildsystem build',
    classifiers = [
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'License :: OSI Approved :: MIT License',
        'Operating System :: POSIX :: Linux',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: Microsoft :: Windows',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Topic :: Software Development :: Build Tools',
    ],
    project_urls = {
        'Source': 'https://github.com/minibuild/minibuild/',
    },
    platforms = ['Linux', 'Windows', 'MacOSX'],
    zip_safe = True
)
