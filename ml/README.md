# ML lab (v0.2)

ML work runs in WSL Ubuntu, not inside the Ollama container. A separate Python
environment per project avoids conflicts between model-serving CUDA libraries and
PyTorch training dependencies. Keep projects, datasets and checkpoints on the Linux
filesystem under `~/projects`, not under `/mnt/c`.

## Create a project environment

If `python3-venv` is installed, use `python3 -m venv .venv`. Without it, these
commands create the same environment without `sudo`, using pip's official package:

```bash
mkdir -p ~/projects/ml-lab && cd ~/projects/ml-lab
python3 -m venv --without-pip .venv
curl -fsSL https://bootstrap.pypa.io/pip/pip.pyz -o /tmp/pip.pyz
.venv/bin/python /tmp/pip.pyz install pip
rm /tmp/pip.pyz
source .venv/bin/activate
python -m pip install jupyterlab ipykernel
```

Take the PyTorch command from https://pytorch.org/get-started/locally/ for Linux, Pip
and a CUDA build your Windows driver supports. Do not install the CUDA Toolkit or a
Linux NVIDIA driver inside WSL.

Tested on RTX 2060 SUPER with Ubuntu 26.04, Python 3.14.4 and the CUDA 13.2 build:

```bash
python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu132
```

The environment takes about 5.6 GB.

## Share the GPU

Chat and ML work take turns on the 8 GB GPU. Stop Ollama before heavy ML work:

```bash
bash scripts/aiws.sh ml
```

Unloading a model is not enough, because a new chat would load it again. When you
finish, close notebook kernels so they release GPU memory, then bring chat back:

```bash
bash scripts/aiws.sh chat
```

## Verify the environment

Run these from the repository root with the project venv active:

```bash
python scripts/check-ml.py
```

```bash
python ml/smoke-train.py --out ~/projects/ml-lab/checkpoints
```

`check-ml.py` runs a real GPU calculation. `smoke-train.py` trains a small network
on generated data, saves a checkpoint and confirms that it reloads correctly. It
proves the toolchain works; it is not a performance or memory benchmark.

## Notebooks

Register the environment as a kernel once, then start JupyterLab on loopback and
keep token protection on. Open the token URL it prints in a Windows browser:

```bash
python -m ipykernel install --user --name ml-lab --display-name "Python (ml-lab)"
```

```bash
jupyter lab --ip=127.0.0.1 --port=8888 --no-browser
```

Remote access from the MacBook is planned for v0.3.
