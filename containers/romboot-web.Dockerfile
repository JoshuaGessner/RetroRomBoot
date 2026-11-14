# RomBoot web appliance: the CLI builder, the Buildroot cross-build toolchain,
# and the stdlib web UI in one image.  Building an image is a runtime action
# that writes to the mounted /cache volume, so this Dockerfile stays small --
# the heavy Buildroot compile happens on the first build request, not here.
FROM debian:bookworm-slim@sha256:7b140f374b289a7c2befc338f42ebe6441b7ea838a042bbd5acbfca6ec875818

ARG DEBIAN_FRONTEND=noninteractive
# Buildroot is pinned by commit in dependencies.lock.json; git content-addressing
# is the integrity check.  Override only in lockstep with the lockfile.
ARG BUILDROOT_COMMIT=135af563b945b8c3d18f8fd370370075b9edb140
ARG BUILDROOT_VERSION=2025.02.16

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

# Fetch exactly the pinned Buildroot release commit and fail closed if the
# fetched HEAD or its declared version does not match the pin.
RUN git init /opt/buildroot \
    && cd /opt/buildroot \
    && git remote add origin https://github.com/buildroot/buildroot.git \
    && git fetch --depth 1 origin "refs/tags/${BUILDROOT_VERSION}" \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "${BUILDROOT_COMMIT}" \
    && grep -q "export BR2_VERSION := ${BUILDROOT_VERSION}" Makefile \
    && rm -rf /opt/buildroot/.git

# Install RomBoot itself.  The project is dependency-free and stdlib-only, so it
# runs straight from the source tree on PYTHONPATH -- no pip, no venv.
COPY . /opt/romboot

# Buildroot refuses to run as root, so the service and every build run as an
# unprivileged user that owns the mutable volumes.
RUN useradd --create-home --uid 1000 builder \
    && mkdir -p /data /cache \
    && chown -R builder:builder /data /cache /opt/romboot

ENV PYTHONPATH=/opt/romboot \
    PYTHONUNBUFFERED=1 \
    BUILDROOT_DIR=/opt/buildroot \
    ROMBOOT_PROJECT_ROOT=/opt/romboot \
    ROMBOOT_WEB_DATA=/data \
    ROMBOOT_WEB_CACHE=/cache \
    ROMBOOT_WEB_HOST=0.0.0.0 \
    ROMBOOT_WEB_PORT=8080

USER builder
WORKDIR /opt/romboot
VOLUME ["/data", "/cache"]
EXPOSE 8080

# The container binds 0.0.0.0 so Docker can publish the port; keep the *host*
# publish bound to 127.0.0.1 (see docker-compose.yml) unless you add a token.
ENTRYPOINT ["python3", "-m", "romboot_web"]
