import setuptools

with open('requirements.txt') as fp:
    install_requires = fp.read()

setuptools.setup(
    packages=setuptools.find_packages(exclude=["tests"]),
    install_requires=install_requires
)
