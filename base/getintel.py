import psutil
import GPUtil

#CPU获取
def cpu(a):
    cpu_xc = psutil.cpu_count(logical=False)
    #线程
    cpu_jc = psutil.cpu_count()
    #CPU频率
    cpu_pl = psutil.cpu_freq()
    #CPU百分比
    cpu_bfb = psutil.cpu_percent(interval=0.8)
    if a == 1:
        return cpu_xc
    elif a == 2:
        return cpu_jc
    elif a == 3:
        return cpu_pl
    elif a == 4:
        return cpu_bfb
    # 1 = 线程 2 = 进程 3 = 频率 4 = 百分比

#内存获取
def nc(a):
    # 拉取内存组件
    vm_nc = psutil.virtual_memory()
    # 内存获取
    GB = 1024 * 1024 * 1024
    # 计算总内存
    vm_z = vm_nc.total / GB
    vm_y = vm_nc.used / GB
    vm_x = vm_nc.available / GB
    # 内存百分比
    vm_bfb = vm_nc.percent
    if a == 1:
        return vm_z
    elif a == 2:
        return vm_bfb
    elif a == 3:
        return vm_y
    elif a == 4:
        return vm_x

    # 1 = 总内存 2 = 占比 3 = 被使用内存 4 = 剩余内存


#GPU获取
def get_gpu_usage(a):
    gpus = GPUtil.getGPUs()
    if not gpus:
        return {"error": "No GPU found"}

    total_util = sum(gpu.load * 100 for gpu in gpus) / len(gpus)
    total_mem_used = sum(gpu.memoryUsed for gpu in gpus) / 1024
    total_mem_total = sum(gpu.memoryTotal for gpu in gpus) / 1024

    if a == 1:
        return total_util
    elif a == 2:
        return total_mem_used
    elif a == 3:
        return total_mem_total
    # 1 = 占比 2 = 被使用内存 3 = 总内存
