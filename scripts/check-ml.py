"""Verify a project-specific PyTorch installation in WSL Ubuntu with real GPU work."""
import sys

try:
    import torch
except ImportError:
    print('PyTorch not installed in this environment. See ml/README.md.')
    raise SystemExit(2)

print('Python:', sys.version.split()[0])
print('PyTorch:', torch.__version__)
print('PyTorch CUDA runtime:', torch.version.cuda)
print('CUDA available:', torch.cuda.is_available())
if not torch.cuda.is_available():
    raise SystemExit('CUDA unavailable; review Windows NVIDIA driver, WSL and the chosen torch wheel.')

print('GPU:', torch.cuda.get_device_name(0))
print('Compute capability:', '.'.join(map(str, torch.cuda.get_device_capability(0))))
print('Compiled architectures:', ' '.join(torch.cuda.get_arch_list()))
free, total = torch.cuda.mem_get_info(0)
print(f'VRAM free before test: {free / 2**20:.0f} / {total / 2**20:.0f} MiB')

# is_available() alone does not prove that a CUDA kernel can run.
x = torch.randn((2048, 2048), device='cuda', dtype=torch.float32)
y = x @ x.T
torch.cuda.synchronize()
if not torch.isfinite(y).all().item():
    raise SystemExit('GPU result is not finite.')
expected = (x[0].double() * x[0].double()).sum().item()
if abs(y[0, 0].item() - expected) > 1e-2 * abs(expected):
    raise SystemExit('GPU result does not match the expected value.')
print('GPU tensor test passed:', tuple(y.shape))
