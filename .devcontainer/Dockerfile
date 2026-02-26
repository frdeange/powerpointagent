FROM mcr.microsoft.com/devcontainers/python:2-3.13-bookworm

# Fix: Remove the expired Yarn classic GPG key and apt source.
# The Yarn repo key (62D54FD4003F6525) has expired, causing apt-get update
# to fail with exit code 100, which breaks feature installations like
# Docker-in-Docker. This removes the problematic source before any
# feature install runs apt-get update.
RUN rm -f /etc/apt/sources.list.d/yarn.list \
    && rm -f /usr/share/keyrings/yarn-keyring.gpg \
    && rm -f /etc/apt/keyrings/yarn.gpg \
    && apt-get update && apt-get clean
