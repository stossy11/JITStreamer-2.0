FROM python:3-alpine

RUN apk add gcc git musl-dev openssl-dev linux-headers #python3-dev
COPY requirements.txt .

RUN pip3 install -r requirements.txt

COPY . .

RUN pip3 install -U -e .
# Don't get recommended deps
# Copy from the source project, not clone it
# get requirements.txt first, get pip deps and then copy the source to build

CMD ["JITStreamer"]
