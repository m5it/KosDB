#!/usr/bin/env python3
"""
KosDB - Setup Script
LevelDB-based database server with authentication, replication, and TLS
"""

import os
import sys
from setuptools import setup, find_packages

# Read version from AUTOVERSION.py if it exists
version = "2.3.0"
try:
    with open('AUTOVERSION.py') as f:
        for line in f:
            if line.startswith('VERSION'):
                version = line.split('=')[1].strip().strip('"').strip("'")
                break
except FileNotFoundError:
    pass

# Read long description
with open('README.md', encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='kosdb',
    version=version,
    description='KosDB - LevelDB-based database server with auth, replication, and TLS',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='KosDB Team',
    url='https://github.com/m5it/KosDB',
    
    packages=find_packages(exclude=['tests', 'benchmarks']),
    
    py_modules=[
        'server',
        'database',
        'commands',
        'parser',
        'auth',
        'binlog',
        'tls_wrapper',
    ],
    
    install_requires=[
        'plyvel>=1.5.0',
        'cryptography>=3.0.0',
    ],
    
    python_requires='>=3.7',
    
    entry_points={
        'console_scripts': [
            'kosdb-server=server:main',
            'kosdb-cli=cli:main',
        ],
    },
    
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Topic :: Database',
        'Topic :: Database :: Database Engines/Servers',
    ],
    
    include_package_data=True,
    zip_safe=False,
)
