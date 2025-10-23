# Lm.py
# 说明：
# - 支持命令行参数覆盖主要配置（方便被外部程序调用）
# - 保持原有流式输出行为（每次 print 使用 flush=True）
# - 以交互式 loop 从 stdin 读取用户输入（可被父进程写入）
# 运行示例（在 Python3.11 环境）:
# python -u Lm.py --model_path path/to/model.gguf --max_tokens 2048

import time
import argparse
import sys

# 以下两个库需要在 Python 3.11 环境中安装
from llama_cpp import Llama
import torch

# ===== 默认配置（可以被命令行参数覆盖） =====
DEFAULT_MODEL_PATH = "D:/aibushu-py/DeepSeek/mode/DeepSeek-R1-Distill-Qwen-7B-IQ4_NL.gguf"
DEFAULT_SYSTEM_PROMPT = "你是一个乐于助人的AI助手，使用简洁清晰的语言回答问题。"

DEFAULT_MAX_TOKENS = 10240
DEFAULT_CPU_THREADS = 8
DEFAULT_GPU_LAYERS = -1
DEFAULT_N_CTX = 40960
DEFAULT_CHUNK_SIZE = 80

# ===== GPU 检测 =====
def gpu_available():
    try:
        return torch.cuda.is_available()
    except Exception:
        return False

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_path", type=str, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--system_prompt", type=str, default=DEFAULT_SYSTEM_PROMPT)
    parser.add_argument("--max_tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--cpu_threads", type=int, default=DEFAULT_CPU_THREADS)
    parser.add_argument("--gpu_layers", type=int, default=DEFAULT_GPU_LAYERS)
    parser.add_argument("--n_ctx", type=int, default=DEFAULT_N_CTX)
    parser.add_argument("--chunk_size", type=int, default=DEFAULT_CHUNK_SIZE)
    return parser.parse_args()

args = parse_args()

MODEL_PATH = args.model_path
SYSTEM_PROMPT = args.system_prompt
MAX_TOKENS = args.max_tokens
CPU_THREADS = args.cpu_threads
GPU_LAYERS = args.gpu_layers
N_CTX = args.n_ctx
CHUNK_SIZE = args.chunk_size

use_gpu = gpu_available()
print(f"检测到 GPU: {'可用' if use_gpu else '不可用'}", flush=True)

# ===== 模型初始化 =====
print("正在加载模型...", flush=True)
start_time = time.time()

try:
    llm = Llama(
        model_path=MODEL_PATH,
        n_gpu_layers=GPU_LAYERS if use_gpu else 0,
        n_threads=CPU_THREADS,
        n_ctx=N_CTX,
        n_batch=512,
        verbose=False
    )
except Exception as e:
    print(f"模型加载失败: {e}", flush=True)
    sys.exit(1)

load_time = time.time() - start_time
print(f"模型加载完成! 耗时: {load_time:.1f} 秒\n", flush=True)

# ===== 对话上下文 =====
conversation = [{"role": "system", "content": SYSTEM_PROMPT}]

# ===== 流式分段输出函数 =====
def print_chunked_stream(text, chunk_size=CHUNK_SIZE):
    """
    保留 AI 自带换行，同时对连续文本超过 chunk_size 自动换行
    """
    buffer = text
    while '\n' in buffer:
        line, buffer = buffer.split('\n', 1)
        while len(line) > chunk_size:
            print(line[:chunk_size], flush=True)
            line = line[chunk_size:]
        print(line, flush=True)
    # 输出剩余部分
    while len(buffer) > chunk_size:
        print(buffer[:chunk_size], flush=True)
        buffer = buffer[chunk_size:]
    if buffer:
        print(buffer, flush=True)

# ===== 生成函数 =====
def generate_response(user_input):
    global conversation
    conversation.append({"role": "user", "content": user_input})

    # 裁剪上下文，保证 token 不超过 N_CTX
    def tokens_len(conv):
        total = 0
        for msg in conv:
            # 注意： llama.tokenize 需要 bytes 参数
            try:
                total += len(llm.tokenize(msg['content'].encode()))
            except Exception:
                # 若 tokenize 不可用或出错，退回到简单字符数估计
                total += len(msg['content'])
        return total

    while tokens_len(conversation) + MAX_TOKENS > N_CTX:
        # 删除最早的非 system 消息
        for i, msg in enumerate(conversation):
            if msg['role'] != "system":
                conversation.pop(i)
                break

    try:
        response_stream = llm.create_chat_completion(
            messages=conversation,
            max_tokens=MAX_TOKENS,
            temperature=0.7,
            stop=["<|im_end|>"],
            stream=True
        )

        full_response = ""
        buffer = ""

        # 一个简单的流式提示前缀，方便 UI 端识别新回复开始
        print("===RESPONSE-BEGIN===", flush=True)
        for chunk in response_stream:
            delta = chunk['choices'][0].get('delta', {})
            if 'content' in delta:
                buffer += delta['content']
                # 每次尝试输出完整行或超过 CHUNK_SIZE 的部分
                while '\n' in buffer or len(buffer) >= CHUNK_SIZE:
                    if '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        print_chunked_stream(line)
                    elif len(buffer) >= CHUNK_SIZE:
                        print(buffer[:CHUNK_SIZE], flush=True)
                        buffer = buffer[CHUNK_SIZE:]
                full_response += delta['content']

        # 输出剩余部分
        if buffer:
            print_chunked_stream(buffer)

        print("===RESPONSE-END===", flush=True)

        # 将 AI 回复加入上下文
        conversation.append({"role": "assistant", "content": full_response})
        return full_response

    except Exception as e:
        err = f"生成错误: {str(e)}"
        print(err, flush=True)
        return err

# ===== 主循环 =====
print("DeepSeek-R1 助手已就绪（输入 'exit' 退出）\n", flush=True)

# 我们保持交互方式：从 stdin 读取每行并作为一次对话输入
# 父进程向子进程发送的每行文本均视为一次 user 输入
try:
    while True:
        # 从 stdin 读取一行
        user_input = sys.stdin.readline()
        if not user_input:
            # 当父进程关闭 stdin，会返回空，这里退出
            break
        user_input = user_input.rstrip("\n")
        if user_input.lower() == 'exit':
            print("助手已退出", flush=True)
            break
        # 记录第一条用户话题（由外部程序处理 undoView）
        start_gen = time.time()
        response = generate_response(user_input)
        gen_time = time.time() - start_gen
        # 统计 tokens 尝试
        try:
            tokens = len(llm.tokenize(response.encode()))
        except Exception:
            tokens = len(response)
        print(f"\n生成耗时: {gen_time:.1f}s | Token: {tokens}", flush=True)

except KeyboardInterrupt:
    print("助手收到中断，退出。", flush=True)
except Exception as e:
    print(f"运行时错误: {e}", flush=True)
