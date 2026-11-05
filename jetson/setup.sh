#!/bin/bash
# Boombox Dream Server - setup on NVIDIA Jetson Orin Nano (Super) with JetPack 6.x
# Run inside the jetson/ folder:   bash setup.sh
# Safe to run again.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
VENV=~/dream-venv
# NVIDIA's PyTorch builds for JetPack 6 / CUDA 12.6. If this address ever changes,
# see https://www.jetson-ai-lab.com and set TORCH_INDEX before running this script.
TORCH_INDEX="${TORCH_INDEX:-https://pypi.jetson-ai-lab.io/jp6/cu126}"

echo "== 1/5 System packages =="
sudo apt update
sudo apt install -y python3-venv python3-pip libopenblas-dev ffmpeg avahi-daemon

echo "== 2/5 Python environment in $VENV =="
python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip wheel

echo "== 3/5 PyTorch for Jetson (from $TORCH_INDEX) =="
"$VENV/bin/pip" install "numpy<2"
"$VENV/bin/pip" install torch torchvision --index-url "$TORCH_INDEX"
"$VENV/bin/python" -c "import torch; assert torch.cuda.is_available(), 'CUDA not available'; print('PyTorch', torch.__version__, 'GPU OK:', torch.cuda.get_device_name(0))"

echo "== 4/5 Whisper + diffusers =="
"$VENV/bin/pip" install -r "$HERE/requirements.txt"
"$VENV/bin/pip" install --no-deps openai-whisper

echo "== 5/5 Start automatically at boot =="
sudo tee /etc/systemd/system/boombox-dream.service >/dev/null <<EOF
[Unit]
Description=Boombox Dream Server (Whisper + SD-Turbo)
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$HERE
ExecStart=$VENV/bin/python $HERE/server.py --save-gallery
Restart=on-failure
RestartSec=10
Environment=HF_HOME=$HOME/.cache/huggingface

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable boombox-dream.service

echo
echo "Done. First start downloads the models (about 3 GB), so give it a few minutes:"
echo "  sudo systemctl start boombox-dream"
echo "  journalctl -u boombox-dream -f        (watch it; 'ready on port 8765' = good)"
echo "Test from any computer:  curl http://$(hostname).local:8765/health"
