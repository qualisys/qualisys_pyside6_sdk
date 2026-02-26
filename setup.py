from setuptools import setup, find_packages

version = "0.1.0"

setup(
    name="qtm-rt-pyside6",
    version=version,
    description="PySide6 SDK for QTM Real-Time Protocol",
    long_description="Qt-based SDK for streaming motion capture data from Qualisys Track Manager",
    url="https://github.com/qualisys/qualisys_pyside6_sdk",
    author="Qualisys AB",
    author_email="support@qualisys.com",
    license="MIT",
    packages=find_packages(),
    install_requires=[
        "PySide6>=6.0.0",
    ],
    classifiers=[
        "Operating System :: OS Independent",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Scientific/Engineering",
        "Topic :: Utilities",
    ],
    python_requires=">=3.10",
    zip_safe=True,
)
