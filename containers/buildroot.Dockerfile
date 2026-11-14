FROM debian:bookworm-slim@sha256:7b140f374b289a7c2befc338f42ebe6441b7ea838a042bbd5acbfca6ec875818

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bc \
        bison \
        build-essential \
        ca-certificates \
        cpio \
        file \
        flex \
        git \
        libncurses-dev \
        locales \
        patch \
        perl \
        python3 \
        rsync \
        unzip \
        wget \
        xz-utils \
        zstd \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 builder
USER builder
WORKDIR /work
