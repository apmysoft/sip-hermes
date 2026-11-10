#!/bin/sh
# Modelos GGUF para llama-swap en HALO (05-11). Root. Idempotente: salta los que ya están con su sha256.
# - "ollama": copia el blob de Ollama (su nombre ES su sha256; se verifica tras copiar). Así Ollama se puede
#   desinstalar después sin perder nada.
# - "hf": descarga de Hugging Face y verifica contra el sha256 LFS publicado.
# Los modelos de Ollama en su formato propio (gpt-oss:20b `gptoss`, qwen3-vl:30b `qwen3vlmoe`) no los carga
# llama.cpp (verificado 05-11): se bajan sus GGUF oficiales.
# Uso: sudo sh modelos.sh
# 05-11 (noche): Ollama desinstalado y /usr/share/ollama borrado. Las líneas "ollama" quedan como procedencia y
# sha256 de los GGUF que ya están en /var/lib/sip-llm/models; para reconstruir desde cero hay que bajar el
# mismo fichero de Hugging Face (origen de la línea) y comprobar que el sha256 coincide.
set -eu
L=/var/lib/sip-llm/models
O=/usr/share/ollama/.ollama/models/blobs
T=/var/lib/sip-llm/staging
while read -r tipo nombre sha origen; do
  case "$tipo" in ''|\#*) continue;; esac
  f=$L/$nombre
  if [ -f "$f" ] && [ "$(stat -c %s "$f")" -gt 0 ] && [ -f "$f.sha256ok" ]; then echo "ya está: $nombre"; continue; fi
  if [ "$tipo" = ollama ]; then
    cp --reflink=auto "$O/sha256-$sha" "$T/$nombre.part"
  else
    curl -sSfL --retry 5 -C - -o "$T/$nombre.part" "https://huggingface.co/$origen/resolve/main/$nombre?download=true" \
      || curl -sSfL --retry 5 -o "$T/$nombre.part" "https://huggingface.co/$origen/resolve/main/$nombre?download=true"
  fi
  echo "$sha  $T/$nombre.part" | sha256sum -c --quiet - || { echo "ERROR sha256: $nombre" >&2; rm -f "$T/$nombre.part"; exit 1; }
  install -o root -g sip-llm -m 640 "$T/$nombre.part" "$f" && rm -f "$T/$nombre.part"
  echo "$sha" > "$f.sha256ok"
  echo "OK $nombre ($(du -h "$f" | cut -f1))"
done <<'EOF'
# tipo   nombre                                        sha256                                                            origen
ollama   qwen3.8-27b-Q4_K_M.gguf                       f5f1dd8920d417aac2718b0bda3403da274301efdd6760b4f0f4b864ff2ad57d  qwen3.8:27b
ollama   mmproj-qwen3.8-27b.gguf                       ac3714bfdddeca31351f2752bf1a63f266f4df87c0b68c895e44945ca704448e  qwen3.8:27b
ollama   qwen3.6-27b-Q4_K_M.gguf                       415aad607fc297a2ad84cda238febbde295f49f17c17ad7784e2246060fb06d0  qwen3.6:27b
ollama   mmproj-qwen3.6-27b.gguf                       c24919d9eb66eda0af3d7a62ef49bef7948389099de880e0cb5eefe2d3c31769  qwen3.6:27b
ollama   qwen3-coder-30b-a3b-Q4_K_M.gguf               1194192cf2a187eb02722edcc3f77b11d21f537048ce04b67ccf8ba78863006a  qwen3-coder:30b
ollama   muse-glimmer-30b-Q4_K_M.gguf                  0d3fc85f61d10fdc84072f0bba6005d61c1ac5605a2627b0fd5ea4ff8194c384  bartowski/Muse-Glimmer-30B-GGUF
ollama   mmproj-muse-glimmer-30b.gguf                  b94be96afc13120bf0636728b75ad568bb4eba5b2096438b009ed032d8cef4ea  bartowski/Muse-Glimmer-30B-GGUF
ollama   qwen3-vl-8b-Q4_K_M.gguf                       9c3e4853af40205c11b5d1000dfcf08e96454adfd872e48b934cd67d59ec3097  qwen3-vl:8b
ollama   mmproj-qwen3-vl-8b.gguf                       9a42417378dd18094b163f529239c42636ef487932f220d8763ab923e6a8a3cb  qwen3-vl:8b
ollama   bge-m3-F16.gguf                               daec91ffb5dd0c27411bd71f29932917c49cf529a641d0168496c3a501e3062c  bge-m3
ollama   qwen3-embedding-0.6b-Q8_0.gguf                06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439  qwen3-embedding:0.6b
hf       gpt-oss-20b-MXFP4.gguf                        27cd6c432c7672cb812a92f611cf3ba7bbc35928262bb1e1253ff4ee6ae35901  ggml-org/gpt-oss-20b-GGUF
hf       Qwen3VL-30B-A3B-Instruct-Q4_K_M.gguf          87bb374d849f80ebdfabb304189fac9e0bd35a0f74506e6a59c51b206cbe863b  Qwen/Qwen3-VL-30B-A3B-Instruct-GGUF
hf       mmproj-Qwen3VL-30B-A3B-Instruct-F16.gguf      cae72cf123cc9e08d553cd5a5055d6d3cf0f82652aa41c3e4aa424cda9a26f7f  Qwen/Qwen3-VL-30B-A3B-Instruct-GGUF
# 06-11: redactor sin censura de automatizaciones-locales (Qwen3.8 27B Heretic/ARA, KL 0,0085; calibrado multilingüe; con MTP)
hf       RVN-Q4_K_M-multilingual-mtp.gguf              8b20771570e85d1988aa3d1574698370a8b79f746eb02b96f25bf05c48f14b95  0bserverx/Qwen3.8-27B-Heretic-Abliterated-Uncensored-GGUF
EOF
echo "TODOS LOS MODELOS OK"
