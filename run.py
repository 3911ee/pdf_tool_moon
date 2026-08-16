"""PDF 工具包 启动脚本"""
import argparse
import uvicorn


def main():
    parser = argparse.ArgumentParser(description="PDF 工具包")
    parser.add_argument("--host", default="127.0.0.1", help="绑定地址 (默认 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8001, help="监听端口 (默认 8001)")
    parser.add_argument("--reload", action="store_true", help="启用热重载")
    args = parser.parse_args()

    uvicorn.run(
        "app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
