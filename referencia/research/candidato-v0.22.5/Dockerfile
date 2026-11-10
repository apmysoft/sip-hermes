# Candidata de evaluación: no sustituye a sip-config/research/Dockerfile. Agente v0.22.5, digest fijado.
FROM nousresearch/hermes-agent@sha256:9c5561579f3ffdf333401797094ac3a743738d6c25d40f4331c7bf77b694238d
RUN cd /tmp \
 && npm pack --silent agent-browser@0.26.0 \
 && test "$(openssl dgst -sha512 -binary agent-browser-0.26.0.tgz | base64 -w0)" = \
         "pdqSfjwbFSp+qnwlb2g23e9wXveIOfMi19xpPA9xZUbzEAUp6W4YBZj6Ybj8z4M7WkcbGDDYc+oDIHDt9R3EDQ==" \
 && npm install -g --ignore-scripts ./agent-browser-0.26.0.tgz \
 && rm agent-browser-0.26.0.tgz \
 && chmod -R a+rX "$(npm root -g)/agent-browser" \
 && chmod a+x "$(npm root -g)"/agent-browser/bin/* \
 && ln -sf "$(npm root -g)/agent-browser/bin/agent-browser.js" /usr/local/bin/agent-browser
