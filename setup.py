#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

requirements = [
    'flask',
    'python-dateutil',
    'sqlalchemy',
]

setup(name='tracker',
      version='0.7',
      install_requires=requirements,
)
