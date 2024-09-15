FROM python:3-alpine

RUN apk add gcc git musl-dev openssl-dev linux-headers libffi-dev cargo zlib-dev #python3-dev

RUN pip3 install -U setuptools pip && git clone https://github.com/Macleykun/JITStreamer-2.0.git && cd JITStreamer-2.0 && pip3 install -U -e .
# Don't get recommended deps
# Copy from the source project, not clone it
# get requirements.txt first, get pip deps and then copy the source to build

CMD ["JITStreamer"]
