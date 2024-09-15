FROM python:3-slim

RUN apt-get update && apt-get install cargo rustc git gcc libssl-dev -y && cargo update -p associative-cache@2.0.0 --precise rustc 1.65

RUN git clone https://github.com/stossy11/JITStreamer-2.0.git && \
    cd JITStreamer-2.0/ && \
    pip3 install -U -e .

# Don't get recommended deps
# Copy from the source project, not clone it
# get requirements.txt first, get pip deps and then copy the source to build

CMD ["JITStreamer"]
