# Setup: Jetson Orin Nano Super (live captions + woodcut pictures)

> Written for JetPack 6.x (Ubuntu 22.04, CUDA 12.6). The server is tested end to end in `--mock` mode; the model part follows the standard Whisper / diffusers APIs but hasn't run on this exact Jetson yet. If a step fails, the error message is the most useful thing to look at.

## 1. Base system

1. Install **JetPack 6.2** following NVIDIA's *Jetson Orin Nano Developer Kit Getting Started* guide. Put the system on the **NVMe SSD** (long M.2 2280 slot on the underside). Models load much faster than from a microSD card.
2. During first setup, choose the hostname `jetson`. Then the Pi finds it as `jetson.local`.
3. Power mode: in the top‑bar power menu pick **MAXN SUPER** (or check `sudo nvpmodel -q`).
4. Optional but helpful on 8 GB: add swap on the SSD, for example:
   ```bash
   sudo fallocate -l 8G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   ```

## 2. Install the dream server

```bash
sudo apt install -y git
git clone https://github.com/<you>/boombox-visuals.git
cd boombox-visuals/jetson
bash setup.sh
```

`setup.sh`:
- creates `~/dream-venv`
- installs **PyTorch for Jetson** from NVIDIA's Jetson AI Lab package index (`TORCH_INDEX`, default `https://pypi.jetson-ai-lab.io/jp6/cu126`) and checks that CUDA works
- installs diffusers, transformers, faster‑whisper and openai‑whisper (`--no-deps`, so it keeps the Jetson PyTorch)
- registers the `boombox-dream` systemd service

If the PyTorch step fails, the index address has probably changed. Look up the current one on jetson-ai-lab.com and run `TORCH_INDEX=<address> bash setup.sh`. Plain `pip install torch` installs a CPU‑only build that won't use the GPU.

## 3. Start and watch

```bash
sudo systemctl start boombox-dream
journalctl -u boombox-dream -f
```

The first start downloads SD‑Turbo and Whisper (~3 GB) and paints one warm‑up image. It's ready when it prints `Boombox Dream Server ready on port 8765 (ai)`.

From any computer on the network:

```bash
curl http://jetson.local:8765/health
```

The log shows what it hears and paints:

```
[hear] 'the last train leaves at midnight' (430 ms)
[paint #12] 'the last train leaves at midnight' in 1.3s
```

All images and their lyrics are kept in `jetson/gallery/`.

## 4. Options

Edit `ExecStart` in `/etc/systemd/system/boombox-dream.service`, then run `sudo systemctl daemon-reload && sudo systemctl restart boombox-dream`.

| Option | Default | |
| --- | --- | --- |
| `--whisper` | `small` | `base` is faster, `medium` hears better but needs more memory |
| `--language` | auto | e.g. `en`, `de`: skips language detection |
| `--translate` | off | captions and pictures in English, whatever language is sung (SD‑Turbo understands English best) |
| `--style "..."` | noir woodcut | the look of every picture, e.g. `"charcoal drawing, bold lines"` |
| `--steps` | `1` | 2–4 = a bit more detail, slower |
| `--size` | `512` | SD‑Turbo is trained at 512 |
| `--model` | `stabilityai/sd-turbo` | any diffusers text‑to‑image model id |
| `--mock` | | no AI, for testing |

On the Pi side (`pi/config.json`): `hear_every_seconds` (2), `hear_window_seconds` (5), `show_captions` (true), `woodcut_levels` (4 flat tones; 0 = smooth greys).

## 5. Alternative: Jetson containers

If native PyTorch is a fight, NVIDIA's **jetson-containers** project ships ready images with PyTorch and diffusers for each JetPack. Inside such a container: `pip install faster-whisper`, then run `python3 server.py` from this folder with port 8765 published.

## Notes

- Whisper on music isn't perfect. Loud mixes and dense vocals give partial or wrong lines, and those show up in the captions too. Instrumental parts keep the last picture. `--language` helps if you know it, and `--whisper medium` hears better if memory allows.
- Memory: Whisper small (~1 GB) + SD‑Turbo fp16 (~3–4 GB) fit in 8 GB shared memory, so close the desktop browser while it runs.
