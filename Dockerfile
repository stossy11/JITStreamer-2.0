FROM python:3.11
# docker run -it --rm -v /var/run:/var/run --cap-add=NET_ADMIN --network=host image
RUN apt-get update && apt-get install --no-install-recommends git gcc libssl-dev -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
# stossy11
RUN git clone https://github.com/Macleykun/JITStreamer-2.0.git

WORKDIR /JITStreamer-2.0/

RUN chmod +x entrypoint.sh && pip3 install -U -e .

ENTRYPOINT ["./entrypoint.sh"]
