FROM python:3.11
# docker run -it --rm -v /var/run:/var/run --device /dev/net/tun --cap-add=NET_ADMIN --cap-add=NET_RAW --network=host image
RUN apt-get update && apt-get install git gcc libssl-dev -y

RUN git clone https://github.com/stossy11/JITStreamer-2.0.git && cd JITStreamer-2.0/ && pip3 install -U -e .

ENTRYPOINT ["JITStreamer"]