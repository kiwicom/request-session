from setuptools import find_packages, setup

with open("requirements.in") as f:
    install_requires = [line for line in f if line and line[0] not in "#-"]

with open("test-requirements.in") as f:
    tests_require = [line for line in f if line and line[0] not in "#-"]

setup(
    name="request_session",
    version="0.9.0",
    url="https://gitlab.skypicker.com/booking/request_session",
    author="Josef Podaný",
    author_email="josef.podany@kiwi.com",
    packages=find_packages(),
    install_requires=install_requires,
    tests_require=tests_require,
    include_package_data=True,
    classifiers=[
        "Operating System :: OS Independent",
        "Topic :: Internet :: WWW/HTTP",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 3",
    ],
)
