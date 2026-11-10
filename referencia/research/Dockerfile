# hermes-research: imagen oficial del agente v0.22.7 (digest) + agent-browser 0.26.0 (sha512) + yt-dlp (sha256).
# Build: docker build -t hermes-research:0.22.7-ab0.26.0-ytdlp2026.10.26 .
# 05-11: sustituye a la receta v2026.9.14 + Dockerfile.ytdlp (esa queda solo para la vuelta atrás).
# Cambios de v0.22.7: Python 3.14 y Chromium/ffmpeg/node dentro de /opt/hermes/tools; usuario interno hermes (10000).
FROM nousresearch/hermes-agent@sha256:e6d81ae52ebf6a43efa529701405509f20054ba818f179ddd748bed4f8af584c
ARG YTDLP_VER=2026.10.26
ARG YTDLP_SHA=a05c5b5d8562f7e8a62f5334348b406af4930d56d3a65f8021d14af0e22339ae
USER root
RUN cd /tmp \
 && npm pack --silent agent-browser@0.26.0 \
 && test "$(openssl dgst -sha512 -binary agent-browser-0.26.0.tgz | base64 -w0)" = \
         "pdqSfjwbFSp+qnwlb2g23e9wXveIOfMi19xpPA9xZUbzEAUp6W4YBZj6Ybj8z4M7WkcbGDDYc+oDIHDt9R3EDQ==" \
 && npm install -g --ignore-scripts ./agent-browser-0.26.0.tgz \
 && rm agent-browser-0.26.0.tgz \
 && chmod -R a+rX "$(npm root -g)/agent-browser" \
 && chmod a+x "$(npm root -g)"/agent-browser/bin/* \
 && ln -sf "$(npm root -g)/agent-browser/bin/agent-browser.js" /usr/local/bin/agent-browser \
 && python3 -c "import urllib.request; urllib.request.urlretrieve('https://files.pythonhosted.org/packages/py3/y/yt-dlp/yt_dlp-${YTDLP_VER}-py3-none-any.whl', 'y.whl')" \
 && echo "${YTDLP_SHA}  y.whl" | sha256sum -c - \
 && python3 -m zipfile -e y.whl /opt/yt-dlp \
 && rm y.whl \
 && chmod -R a+rX /opt/yt-dlp \
 && PYTHONPATH=/opt/yt-dlp python3 -m yt_dlp --version
USER 995:985
