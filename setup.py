from setuptools import setup, find_packages

setup(
    name="localuseragent",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "loguru",
        "json5",
        "pydantic",
        "psutil",
        "fastapi",
        "uvicorn",
        "httpx",
        "aio_pika",
        "requests",
        "dotenv",
        "aiohttp",
        "apscheduler"
        # 其他依赖...
    ],
    classifiers=[  # 分类信息，便于PyPI分类
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.11',  # 指定Python版本要求
) 