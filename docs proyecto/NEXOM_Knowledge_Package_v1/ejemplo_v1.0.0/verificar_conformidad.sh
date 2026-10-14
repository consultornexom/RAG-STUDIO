#!/usr/bin/env bash
# Verificación reproducible de conformidad — NEXOM Knowledge Package v1.0.0
#
# Ejecutar desde la carpeta ejemplo_v1.0.0/ (hermana de contrato_v1.0.0/):
#     pip install -r requirements.lock.txt
#     bash verificar_conformidad.sh
#
# Comprueba, sin modificar ningún archivo publicado:
#   1. los 16 artefactos normativos contra contrato_v1.0.0/SHA256SUMS;
#   2. los hashes de los artefactos QA y del ejemplo contra SHA256SUMS_EJEMPLO;
#   3. el validador de referencia sobre el directorio y el ZIP del ejemplo,
#      con y sin --trusted-key-id (0 errores esperados);
#   4. la suite automatizada (19 casos negativos + caso base = 20/20).
# Sale con código distinto de 0 si cualquier comprobación falla.
set -u
export PYTHONDONTWRITEBYTECODE=1   # no escribir __pycache__ dentro de las carpetas publicadas

HERE="$(cd "$(dirname "$0")" && pwd)"
CONTRATO="$HERE/../contrato_v1.0.0"
PKG="nexom-knowledge-package-demo-v1.0.0"
FAIL=0

echo "== 1. Artefactos normativos (contrato_v1.0.0/SHA256SUMS)"
(cd "$CONTRATO" && sha256sum -c SHA256SUMS) || FAIL=1

echo "== 2. Ejemplo y QA (SHA256SUMS_EJEMPLO)"
(cd "$HERE" && sha256sum -c SHA256SUMS_EJEMPLO) || FAIL=1

# Árbol temporal con la disposición que esperan el validador y la suite:
# schemas/, common/, validator/ (del contrato publicado) + example_package/, delivery/.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cp -r "$CONTRATO/schemas" "$CONTRATO/common" "$CONTRATO/validator" "$TMP/"
cp "$HERE/qa/test_negative_cases.py" "$TMP/validator/"
cp -r "$HERE/example_package" "$HERE/delivery" "$TMP/"
cp "$HERE/$PKG.zip" "$TMP/"

cd "$TMP"
D="delivery/$PKG"
KID="$(python3 -c "import json;print(json.load(open('$D.sig'))['key_id'])")"
COMMON=(--content-digest-file "$D.content.sha256" --signature-file "$D.sig" --public-key "$D.pubkey_DEMO.pem")

run() {
  local label="$1"; shift
  local out rc
  out="$(python3 validator/validate_knowledge_package.py "$@" 2>&1)"; rc=$?
  echo "$label: $(echo "$out" | grep -E '^(OK|ERRORES):' | tr '\n' ' ')exit=$rc"
  [ "$rc" -eq 0 ] || { FAIL=1; echo "$out" | grep ERROR; }
}

echo "== 3. Validador de referencia"
run "directorio"                 example_package "${COMMON[@]}"
run "directorio + trusted-key-id" example_package "${COMMON[@]}" --trusted-key-id "$KID"
run "zip"                        "$PKG.zip" "${COMMON[@]}" --zip-sha256-file "$D.zip.sha256"
run "zip + trusted-key-id"       "$PKG.zip" "${COMMON[@]}" --zip-sha256-file "$D.zip.sha256" --trusted-key-id "$KID"

echo "== 4. Suite positiva y negativa"
SUITE="$(python3 validator/test_negative_cases.py 2>/dev/null)"; rc=$?
echo "$SUITE"
[ "$rc" -eq 0 ] || FAIL=1

echo
if [ "$FAIL" -eq 0 ]; then echo "CONFORMIDAD v1.0.0: PASS"; else echo "CONFORMIDAD v1.0.0: FAIL"; fi
exit "$FAIL"
