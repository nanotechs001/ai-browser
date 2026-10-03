FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      chromium fonts-noto-core fonts-noto-cjk fonts-noto-color-emoji fonts-liberation \
      python3 python3-pip python3-venv nodejs npm \
      curl jq socat ca-certificates procps \
 && rm -rf /var/lib/apt/lists/*

# Two users: Chromium runs as `browser` and alone owns the logged-in profile; the agent's shell runs as
# `agent` in a separate container that never mounts /profile.
RUN useradd --create-home --uid 1000 --shell /bin/bash browser \
 && useradd --create-home --uid 1001 --shell /bin/bash agent \
 && mkdir -p /profile /work /skills \
 && chown browser:browser /profile && chmod 700 /profile \
 && chmod 1777 /work

COPY entrypoint.sh /usr/local/bin/aib-entrypoint
COPY cdp_proxy.py /usr/local/bin/aib-cdp-proxy
# A copy made without git (a ZIP) may carry CRLF endings; the scripts must reach Linux with LF.
RUN sed -i 's/\r$//' /usr/local/bin/aib-entrypoint /usr/local/bin/aib-cdp-proxy
RUN chmod 755 /usr/local/bin/aib-entrypoint /usr/local/bin/aib-cdp-proxy

USER browser
WORKDIR /work
EXPOSE 9223
ENTRYPOINT ["/usr/local/bin/aib-entrypoint"]
