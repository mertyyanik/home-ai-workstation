"""Short GPU training smoke test: train, save a checkpoint, reload and compare.

Uses generated data, so nothing is downloaded. Run with the project venv active:

    python ml/smoke-train.py --out ~/projects/ml-lab/checkpoints
"""
import argparse
import pathlib
import time

import torch
from torch import nn


def build_model():
    return nn.Sequential(
        nn.Conv2d(1, 16, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
        nn.Conv2d(16, 32, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
        nn.Flatten(), nn.Linear(32 * 8 * 8, 2),
    )


def make_batch(batch_size, device):
    """Label each image by whether its bright square is in the left or right half."""
    images = torch.randn(batch_size, 1, 32, 32, device=device) * 0.3
    labels = torch.randint(0, 2, (batch_size,), device=device)
    for side in (0, 1):
        rows = labels == side
        images[rows, :, 12:20, side * 16 + 4:side * 16 + 12] += 1.0
    return images, labels


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=pathlib.Path, required=True, help='checkpoint folder')
    parser.add_argument('--steps', type=int, default=300)
    parser.add_argument('--batch-size', type=int, default=128)
    args = parser.parse_args()

    if not torch.cuda.is_available():
        raise SystemExit('CUDA unavailable; run scripts/check-ml.py first.')
    device = torch.device('cuda')
    torch.manual_seed(0)

    model = build_model().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_function = nn.CrossEntropyLoss()

    start = time.perf_counter()
    first_loss = last_loss = None
    for step in range(1, args.steps + 1):
        images, labels = make_batch(args.batch_size, device)
        loss = loss_function(model(images), labels)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        last_loss = loss.item()
        if first_loss is None:
            first_loss = last_loss
        if step % 100 == 0:
            print(f'step {step}: loss {last_loss:.4f}')
    torch.cuda.synchronize()
    seconds = time.perf_counter() - start
    print(f'Trained {args.steps} steps in {seconds:.1f}s; peak VRAM '
          f'{torch.cuda.max_memory_allocated() / 2**20:.0f} MiB')
    if last_loss >= first_loss:
        raise SystemExit(f'Loss did not improve: {first_loss:.4f} to {last_loss:.4f}.')

    args.out.mkdir(parents=True, exist_ok=True)
    checkpoint = args.out / 'smoke-train.pt'
    torch.save({'model': model.state_dict(), 'steps': args.steps}, checkpoint)

    # A checkpoint only counts if a new model reproduces the same outputs from it.
    model.eval()
    restored = build_model().to(device)
    restored.load_state_dict(torch.load(checkpoint, map_location=device)['model'])
    restored.eval()
    images, labels = make_batch(1024, device)
    with torch.no_grad():
        expected, actual = model(images), restored(images)
    if not torch.equal(expected, actual):
        raise SystemExit('Reloaded checkpoint gives different outputs.')
    accuracy = (actual.argmax(1) == labels).float().mean().item()
    print(f'Checkpoint reloaded: {checkpoint}')
    print(f'Accuracy on new generated data: {accuracy:.3f}')
    if accuracy < 0.9:
        raise SystemExit('Accuracy is below 0.9; training did not work as expected.')
    print('Smoke training passed.')


if __name__ == '__main__':
    main()
