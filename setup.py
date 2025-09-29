from io import open

from setuptools import find_packages, setup

with open("README.md", encoding="utf-8") as f:
    readme = f.read()

with open("requirements.in", encoding="utf-8") as f:
    install_requires = [line for line in f if line and line[0] not in "#-"]

with open("test-requirements.in", encoding="utf-8") as f:
    tests_require = [line for line in f if line and line[0] not in "#-"]

setup(
    name="request_session",
    version="0.16.4",
    url="https://github.com/kiwicom/request-session",
    description="Python HTTP requests on steroids",
    long_description=readme,
    long_description_content_type="text/markdown",
    author="Kiwi.com platform team",
    author_email="platform@kiwi.com",
    packages=find_packages(exclude=["test*"]),
    install_requires=install_requires,
    extras_require={
        "test": tests_require,
    },
    include_package_data=True,
    classifiers=[
        "Development Status :: 4 - Beta",
        "Operating System :: OS Independent",
        "Topic :: Internet :: WWW/HTTP",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Intended Audience :: Developers",
    ],
)
