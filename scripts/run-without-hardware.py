#!/usr/bin/env python3
"""Own both child processes; use real HTTP/auth/AI and a separate synthetic DB."""
import os
import argparse
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from dotenv import dotenv_values
import httpx

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Verify one synthetic HTTP upload, then stop both processes")
    args = parser.parse_args()
    os.chdir(ROOT)
    os.umask(0o077)
    if subprocess.run([sys.executable, "scripts/configure-accounts.py", "--check"]).returncode:
        raise SystemExit("先打开 setup-and-demo.command 完成账号密码设置。")
    config = {key:value for key,value in dotenv_values(os.environ.get("CARELINK_ENV_FILE", ROOT / ".env"), interpolate=False).items() if value is not None}
    port = int(os.environ.get("CARELINK_DEMO_PORT", "8000"))
    database = Path(os.environ.get("CARELINK_SIMULATION_DATABASE", ROOT / "backend/carelink-simulation.db")).resolve()
    hardware_database = (ROOT / config.get("CARELINK_DATABASE_PATH", "backend/carelink.db")).resolve()
    if database in {hardware_database, (ROOT.parent / "server/sensor_data.db").resolve()}:
        raise SystemExit("模拟演示必须使用独立数据库。")
    # No fake readings ever enter backend/carelink.db or the old sensor database.
    env = {**os.environ, **config, "CARELINK_BIND_HOST":"127.0.0.1", "CARELINK_PORT":str(port),
           "CARELINK_SIMULATION":"1", "CARELINK_DATABASE_PATH":str(database)}
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            raise SystemExit("演示端口已有服务。请先停止它，避免把模拟数据发送到其他数据库。")
    children = []
    def stop(_signum, _frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, stop)
    try:
        children.append(subprocess.Popen([sys.executable, "scripts/serve-local.py"], env=env))
        deadline = time.monotonic() + 40
        while True:
            if children[0].poll() is not None:
                raise RuntimeError("HTTP 后端未能启动；未启动模拟数据。")
            try:
                response = httpx.get(f"http://127.0.0.1:{port}/health", trust_env=False, timeout=2)
                if response.status_code == 200 and response.json().get("simulation") is True:
                    break
            except httpx.HTTPError:
                pass
            if time.monotonic() > deadline:
                raise RuntimeError("HTTP 健康检查超时；未启动模拟数据。")
            time.sleep(.2)
        command = ["node", "scripts/simulate-sensor.mjs", f"--url=http://127.0.0.1:{port}/sensor-data"]
        if args.check:
            command += ["--count=1", "--scenario=normal"]
        children.append(subprocess.Popen(command, env=env))
        if args.check:
            return children[-1].wait(timeout=25)
        print(f"HTTP 模拟演示已启动：http://127.0.0.1:{port}", flush=True)
        print("只监听本机；使用独立模拟数据库。模拟器发送 HTTP 请求，后端照常运行 LR/CNN 逻辑。", flush=True)
        print("当前模拟器生成生命体征场景；CNN 运动窗口另由回归测试验证，不冒充真实硬件数据。", flush=True)
        if sys.platform == "darwin" and os.environ.get("CARELINK_NO_BROWSER") != "1":
            subprocess.run(["open", f"http://127.0.0.1:{port}"], check=False)
        while all(process.poll() is None for process in children):
            time.sleep(.5)
        raise RuntimeError("演示子进程已退出；正在一起停止，避免留下后台服务。")
    except KeyboardInterrupt:
        print("正在停止演示。", flush=True)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1
    finally:
        for process in reversed(children):
            if process.poll() is None:
                process.terminate()
        for process in reversed(children):
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
