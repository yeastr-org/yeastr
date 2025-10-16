import sys
import setuptools


classifiers = [
    "Programming Language :: Python :: 3",
    "Operating System :: OS Independent",
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",  # cool flexible stuff
    "Intended Audience :: System Administrators",  # backporting/compatibility
    "Intended Audience :: Telecommunications Industry",  # needs this imho
    "Topic :: Software Development",
    # "License :: OSI Approved :: Python Software Foundation License 2.0",
    *[f"Programming Language :: Python :: 3.{n}" for n in range(8, 15)],
]


setuptools.setup(
    classifiers=classifiers,
    packages=["yeastr"],
)
