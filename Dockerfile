# The build-stage image:
FROM condaforge/mambaforge AS build

# test some things
RUN conda --version
RUN apt-get update -y
RUN apt-get install -y iputils-ping
RUN ping -c 1 dns.google

# Install the package as normal:
COPY myflask.yaml .
RUN mamba env create -f myflask.yaml

# Install conda-pack:
RUN conda install -c conda-forge conda-pack

# Use conda-pack to create a standalone enviornment
# in /venv:
RUN conda-pack -n myflask -o /tmp/env.tar && \
  mkdir /venv && cd /venv && tar xf /tmp/env.tar && \
  rm /tmp/env.tar

# We've put venv in same path it'll be in final image,
# so now fix up paths:
RUN /venv/bin/conda-unpack


# The runtime-stage image; we can use Debian as the
# base image since the Conda env also includes Python
# for us.
FROM ubuntu:focal AS runtime

RUN apt-get update && \
    apt-get install -yq tzdata && \
    ln -fs /usr/share/zoneinfo/Europe/Amsterdam /etc/localtime && \
    dpkg-reconfigure -f noninteractive tzdata

# Set locale
RUN apt-get install -y locales

# Set the locale
RUN sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen && \
    locale-gen
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

# Copy /venv from the previous stage:
COPY --from=build /venv /venv

# When image is run, run the code with the environment
# activated:
SHELL ["/bin/bash", "-c"]

WORKDIR /ngsweb
COPY . /ngsweb/
