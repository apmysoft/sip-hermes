# Límites del worker HALO

Fragmento destinado a `/etc/systemd/system/user-995.slice.d/50-sip-worker-limits.conf`,
root:root 0644. UID 995 es el de hermes-worker en HALO; verificarlo antes de instalar.
No aplicar en Neo ni a otro UID. No cambia sshd, launcher ni otras slices.

Baseline experimental: CPUQuota=400% equivale al tiempo agregado de cuatro CPU,
sin reservar núcleos ni limitar afinidad. MemoryMax=8G y MemorySwapMax=0 contienen
RAM/swap; TasksMax=256 cuenta tareas/hilos. Todos son topes compartidos entre
sesiones y servicios del usuario (también su gestor, PipeWire y portales observados).
No son cuatro CPU ni 8 GiB por comando. Un OOM puede terminar procesos del worker.
No incluye límite de disco ni cambia el timeout de 300 segundos del launcher.

Verificado antes de preparar: cgroups v2 y controladores cpu/memory/pids presentes;
SSH usa PAM y pam_systemd. Una sesión real desde la candidata sitúa sshd, timeout,
bwrap y sleep bajo `/user.slice/user-995.slice/session-1023.scope`.

Instalado en HALO el 2026-10-07, root:root 0644, con daemon-reload. Nueva sesión
SSH 1025 bajo la slice activa: cpu.max=400000 100000, memory.max=8589934592,
memory.swap.max=0 y pids.max=256 verificados en el kernel. Prueba funcional SSH
conserva UID/GID 995:982, /workspace y lectura del testigo. No se probaron carga
CPU, OOM ni agotamiento de tareas. Persistencia tras reboot pendiente en ventana
acordada; el disco sigue sin un límite aplicado.

Rollback: conservar fuera de systemd el fragmento instalado, ejecutar daemon-reload
y restablecer/verificar topes anteriores en la slice. Retirar un archivo no prueba
que se hayan eliminado límites de un cgroup que ya estaba activo; no interrumpir
sesiones ni detener user-995.slice sin acordarlo.
