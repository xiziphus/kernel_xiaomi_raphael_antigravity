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
