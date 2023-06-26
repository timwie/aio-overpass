# Contributing
I'm still in the process of writing this page :construction:

<!--
https://mozillascience.github.io/working-open-workshop/contributing/
https://gist.github.com/PurpleBooth/b24679402957c63ec426
https://github.com/auth0/open-source-template/blob/master/GENERAL-CONTRIBUTING.md
https://contribute.cncf.io/maintainers/templates/contributing/
https://opensource.ieee.org/community-handbook/community-processes/templates/contributing/-/blob/main/contributing_howto.md

https://gitlab.com/tgdp/templates/-/blob/main/contributing-guide/about-contributing-guide.md
https://gitlab.com/tgdp/templates/-/blob/main/contributing-guide/template-contributing-guide.md
-->

<br>

## Dev Environment
The build tool used for this project is [Poetry]. Follow [these steps](https://python-poetry.org/docs/#installation)
to install it if you haven't already.

A good next step is to setup a virtual environment. I personally like to use [pyenv] for that,
since it makes it easy to switch between multiple versions of Python.
You can follow [these steps](https://github.com/pyenv/pyenv#installation)
to set it up. Afterwards you can create a dedicated venv like this:

```console
$ pyenv install 3.9.17
$ pyenv virtualenv 3.9.17 aio-overpass39
```

From now on, make sure that the venv is activated: `$ pyenv activate aio-overpass39`.
If you're using Pycharm, set the interpreter to `~/.pyenv/versions/aio-overpass39/bin/python`,
and it will always be activated in any terminal inside the IDE.

Next up, clone the repository, and install the project and all dependencies:

```console
$ git clone git@github.com:timwie/aio-overpass.git
$ cd aio-overpass/
$ poetry install --all-extras --with notebooks
```

This will also install [Invoke], a neat little task runner. Here is a
list of tasks you can run with `$ invoke <task>`:

```console
$ invoke -l
Available tasks:

  doc            Generate documentation
  doco           Generate documentation and open in browser
  fmt            Run code formatters
  install        Install all dependencies
  lint           Run linter and type checker
  papermill      Generate example notebooks with papermill
  test           Run tests
  test-publish   Perform a dry run of publishing the package
  update         Update dependencies
```

Finally, you want to prepare [JupyterLab] by setting up a kernel
specific to this venv:

```console
$ ipython kernel install --user --name=aio-overpass
```

From now on you can use `$ jupyter-lab` and play around with
`aio_overpass` in notebooks.

[Poetry]: https://python-poetry.org/
[pyenv]: https://github.com/pyenv/pyenv
[Invoke]: https://github.com/pyinvoke/invoke
[JupyterLab]: https://jupyter.org/
