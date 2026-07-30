FROM ubuntu:22.04

ARG DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update && apt-get install -y \
    bc \
    bison \
    build-essential \
    curl \
    flex \
    git \
    gnupg \
    gperf \
    liblz4-tool \
    libncurses5-dev \
    libsdl1.2-dev \
    libssl-dev \
    libwxgtk3.0-gtk3-dev \
    libxml2 \
    libxml2-utils \
    lzop \
    pngcrush \
    rsync \
    schedtool \
    squashfs-tools \
    xsltproc \
    zip \
    zlib1g-dev \
    python3 \
    python3-pip \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install Clang and LLVM
RUN apt-get update && apt-get install -y clang lld llvm

# ccache. build_kernel_soviet_docker.sh sets USE_CCACHE=1 and CCACHE_DIR and
# prints "ccache enabled", but ccache was never actually installed here, so the
# cache stayed empty and every rebuild recompiled the whole tree from cold.
# The kernel is built with the AOSP prebuilt at /opt/clang, not a distro clang,
# so the stock /usr/lib/ccache symlinks (gcc/g++/cc/c++ only) do not help --
# the build script invokes ccache explicitly via CC instead.
RUN apt-get update && apt-get install -y ccache && rm -rf /var/lib/apt/lists/*

# cpio and zstd are required by kernel/gen_kheaders.sh, which runs whenever
# CONFIG_IKHEADERS=y (it is, on the InfinityX config). Without cpio the build
# dies late with an opaque exit 127:
#   make[2]: *** [kernel/Makefile:135: kernel/kheaders_data.tar.xz] Error 127
# rsync is needed to stage the source tree onto tmpfs.
RUN apt-get update && apt-get install -y cpio zstd rsync && rm -rf /var/lib/apt/lists/*

# Install GCC cross-compilers (required for some kernel builds even with Clang)
RUN apt-get update && apt-get install -y \
    gcc-aarch64-linux-gnu \
    gcc-arm-linux-gnueabi

# Set up working directory
WORKDIR /kernel

# Create a user to avoid running as root (optional but recommended)
# ARG USER_ID=1000
# ARG GROUP_ID=1000
# RUN groupadd -g ${GROUP_ID} builder && \
#     useradd -m -u ${USER_ID} -g builder -s /bin/bash builder
# USER builder

CMD ["/bin/bash"]
