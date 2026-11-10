# Runner aislado de ejecución sobre la red Docker `sandbox` (172.30.0.0/24).
# Aislamiento de red: internal=true + drop total de origen 172.30 en nftables (sip-zones).
# sshd escucha en el 2222 porque con cap_drop ALL no existe CAP_NET_BIND_SERVICE
# para el puerto 22; no hay ports publicados, el puerto solo es alcanzable
# dentro de la red sandbox (y desde sip mediante la excepción nft acordada).
FROM debian@sha256:7ff6ba31527b9e336162fa061746c366c4b2032f4d2cff2078bea43f78efe3f8

RUN apt-get update \
 && apt-get install -y --no-install-recommends openssh-server openssh-client iproute2 ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && (useradd --uid 1001 --create-home --shell /bin/bash sandbox || true) \
 && (useradd --system --no-create-home --shell /usr/sbin/nologin sshd || true) \
 && usermod -p '*' sandbox \
 && mkdir -p /run/sshd /etc/ssh/hostkeys /home/sandbox/.ssh \
 && chmod 755 /home/sandbox/.ssh

COPY sshd_config /etc/ssh/sshd_config
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 0755 /usr/local/bin/entrypoint.sh

# /workspace es el volumen de trabajo persistido; los host keys viven en su
# volumen para sobrevivir recreaciones del contenedor sin reescribir known_hosts.
VOLUME ["/workspace", "/etc/ssh/hostkeys"]

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
