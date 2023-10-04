from setuptools import setup


with open('README.md', 'r', encoding='utf-8') as f:
    long_description = f.read()


setup(
    # metadata
    name='py-huff',
    version='0.0.1',
    description='A compiler for the Huff EVM assembly language written in Python',
    long_description_content_type='text/markdown',
    long_description=long_description,
    packages=[],
    classifiers=[
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.10'
    ],
    author='Philogy',
    url='https://github.com/Philogy/py-huff',
    # actual data
    entry_points={
        'console_scripts': ['huffy = py_huff.cli:main']
    },
    install_requires=[
        'parsimonious >= 0.9.0',
        'types-parsimonious >= 0.10.0.9',
        'pycryptodome >= 3.19.0'
    ],
    package_data={'py-huff': ['py.typed']}
)
