FROM docker.m.daocloud.io/library/python:3.11-slim

WORKDIR /code

# 时区
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 安装依赖
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# 复制项目
COPY ./app /code/app

# 数据目录（SQLite）
RUN mkdir -p /code/data

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]