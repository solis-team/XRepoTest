"""
Host vLLM Server

This script launches an OpenAI-compatible API server using vLLM.
It is a wrapper around `vllm.entrypoints.openai.api_server`.

Usage:
    python host_vllm.py --model <model_path> --port 8000 --tensor-parallel-size <N>
"""

import os
import sys
import argparse
import subprocess

def main():
    parser = argparse.ArgumentParser(description="Host vLLM OpenAI-compatible Server")
    parser.add_argument("--model", type=str, required=True, help="Path to the model or HuggingFace model name")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host interface (default: 0.0.0.0)")
    parser.add_argument("--tensor-parallel-size", "-tp", type=int, default=1, help="Number of GPUs to use")
    parser.add_argument("--max-model-len", type=int, default=None, help="Maximum context length")
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.9, help="GPU memory utilization (0.0 - 1.0)")
    parser.add_argument("--trust-remote-code", action="store_true", help="Trust remote code from HuggingFace")
    
    # Parse known args, pass the rest to vLLM
    args, unknown_args = parser.parse_known_args()
    
    print(f"Starting vLLM server for model: {args.model}")
    print(f"Listening on {args.host}:{args.port}")
    print(f"Tensor Parallel Size: {args.tensor_parallel_size}")
    
    # improved vllm command construction
    cmd = [
        sys.executable, "-m", "vllm.entrypoints.openai.api_server",
        "--model", args.model,
        "--port", str(args.port),
        "--host", args.host,
        "--tensor-parallel-size", str(args.tensor_parallel_size),
        "--gpu-memory-utilization", str(args.gpu_memory_utilization)
    ]
    
    if args.max_model_len:
        cmd.extend(["--max-model-len", str(args.max_model_len)])
        
    if args.trust_remote_code:
        cmd.append("--trust-remote-code")
        
    # Append any extra arguments
    cmd.extend(unknown_args)
    
    print(f"Executing command: {' '.join(cmd)}")
    print("-" * 60)
    
    try:
        # Run the server process
        # We use subprocess.run to keep it running in foreground so we can see logs
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\nServer stopped by user.")
    except Exception as e:
        print(f"\nError running server: {e}")
        return 1
        
    return 0

if __name__ == "__main__":
    sys.exit(main())
