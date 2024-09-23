FROM python:3.11
# docker run -it --rm -v /var/run:/var/run --device /dev/net/tun --cap-add=NET_ADMIN --cap-add=NET_RAW --network=host image
RUN apt-get update && apt-get install git gcc libssl-dev -y

#RUN apt-get update && apt-get install cargo rustc git gcc libssl-dev -y
RUN curl https://sh.rustup.rs -sSf | \
    sh -s -- --default-toolchain stable -y

ENV PATH=/root/.cargo/bin:$PATH

RUN git clone https://github.com/stossy11/JITStreamer-2.0.git && cd JITStreamer-2.0/ && pip3 install -U -e .

ENTRYPOINT ["JITStreamer"]
