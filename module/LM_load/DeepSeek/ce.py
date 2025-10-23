import torch
import os

print(f"PyTorch 版本: {torch.__version__}")
print(f"PyTorch 是否可用 CUDA? {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"PyTorch CUDA 版本: {torch.version.cuda}")
    print(f"PyTorch 检测到的 GPU 数量: {torch.cuda.device_count()}")
    if torch.cuda.device_count() > 0:
        print(f"当前 GPU 型号 (PyTorch): {torch.cuda.get_device_name(0)}")
quit()








