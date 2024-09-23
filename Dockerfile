FROM python:3.11
# docker run -it --rm -v /var/run:/var/run --cap-add=NET_ADMIN --network=host image
RUN apt-get update && apt-get install git gcc libssl-dev -y

COPY entrypoint.sh .

RUN chmod +x entrypoint.sh && git clone https://github.com/stossy11/JITStreamer-2.0.git && cd JITStreamer-2.0/ && pip3 install -U -e .

ENTRYPOINT ["/entrypoint.sh"]