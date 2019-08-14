# request_session

| What          | Where                                                           |
| ------------- | --------------------------------------------------------------- |
| Documentation | <https://kiwi.wiki/booking/request_session>                     |
| Discussion    | [plz-booking](https://skypicker.slack.com/messages/plz-booking) |
| Maintainer    | [Josef Podaný](<https://gitlab.skypicker.com/Josef Podaný>)     |

## Initial setup

This repo was created from a cookiecutter template.
Here are some instructions from the creators of that template:

1. If you need to use our internal PyPI,
   set the `PYPI_USERNAME` and `PYPI_PASSWORD` secret CI variables
   in the [GitLab project settings](https://gitlab.skypicker.com/bookingrequest_session).
2. [Configure GitLab repository.](https://kiwi.wiki/kiwi/handbook/#/how-to/configure-repository-in-gitlab)
3. Write documentation usage section.
4. Remove this section from the README.

## Usage

*TODO!*

## Code formatting

In order to maintain code formatting consistency we use [black](https://github.com/ambv/black/)
to format the python files. A pre-commit hook that formats the code is provided but it needs to be
installed on your local git repo, so...

In order to install the pre-commit framework run `pip install pre-commit`
or if you prefer homebrew `brew install pre-commit`

Once you have installed pre-commit just run `pre-commit install` on your repo folder

If you want to exclude some files from Black (e.g. automatically generated
database migrations or test [snapshots](https://github.com/syrusakbary/snapshottest))
please follow instructions for [pyproject.toml](https://github.com/ambv/black#pyprojecttoml)

## Testing

To run all tests:

```
tox
```

Note that tox doesn't know when you change the `requirements.txt`
and won't automatically install new dependencies for test runs.
Run `pip install tox-battery` to install a plugin which fixes this silliness.

## Contributing

Create a merge request and assign it to Josef Podaný for review.
Ping Josef Podaný in the discussion channel linked above.
