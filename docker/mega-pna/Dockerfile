# CUDA benchmark environment aligned with the official MEGA-GNN runtime.
FROM pytorch/pytorch:2.2.2-cuda11.8-cudnn8-runtime

WORKDIR /workspace

COPY requirements-mega-pna-cuda118.txt /tmp/requirements-mega-pna-cuda118.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements-mega-pna-cuda118.txt

COPY src /workspace/src
COPY scripts /workspace/scripts

ENV PYTHONPATH=/workspace

ENTRYPOINT ["python", "scripts/benchmark_mega_pna.py"]
CMD ["--suite", "gate", "--device", "cuda", "--include-ablation"]
