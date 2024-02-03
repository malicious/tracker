#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup

packages = [
    'tracker',
    'notes_v2',
]

requirements = [
    'flask>=2.3',
    'python-dateutil',
    'sqlalchemy',
]

setup(name='tracker',
      version='1.4',
      install_requires=requirements,
      packages=packages,
      python_requires='>=3',
      extras_require={
          'prod': ['hypercorn'],
          'uvicorn': ['asgiref', 'uvicorn', 'uvloop'],
          'markdown': ['markdown-it-py'],
      },
)
