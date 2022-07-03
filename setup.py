#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup

packages = [
    'tracker',
    'notes_v2',
    'tasks_v2',
]

requirements = [
    'flask>=2.1',
    'python-dateutil',
    'sqlalchemy',
]

setup(name='tracker',
      version='0.7',
      install_requires=requirements,
      packages=packages,
      python_requires='>=3',
)
