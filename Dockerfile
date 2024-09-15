FROM python:3.11-slim-bookworm
# Get smaller image, preferabbly the alpine 3.11/3

RUN apt update && apt install git gcc libssl-dev -y  && \
  git clone https://github.com/stossy11/JITStreamer-2.0.git && \
  cd JITStreamer-2.0/ && \
  pip3 install -U -e .
# Don't get recommended deps
# Copy from the source project, not clone it
# get requirements.txt first, get pip deps and then copy the source to build

CMD ["JITStreamer"]