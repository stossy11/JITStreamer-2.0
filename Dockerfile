FROM python:3.11
# Build this locally, run it with: docker run -it --rm -v /var/run:/var/run --device /dev/net/tun --cap-add=NET_ADMIN --cap-add=NET_RAW --network=host image
# You'll get thrown into a bash shell, you can run JITstreamer --pair . This is WIP and locally on my rpi 4 it worked (aarch64)
RUN apt-get update && apt-get install git gcc libssl-dev -y

#RUN apt-get update && apt-get install cargo rustc git gcc libssl-dev -y
RUN curl https://sh.rustup.rs -sSf | bash -s -- -y

RUN git clone https://github.com/stossy11/JITStreamer-2.0.git && cd JITStreamer-2.0/ && pip3 install -U -e .

ENTRYPOINT ["JITStreamer"]
