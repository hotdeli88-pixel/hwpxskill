#!/usr/bin/env bash
# rhwp(HWP/HWPX 뷰어·변환기, MIT) 설치 — Mac·Linux용.
# hwpxskill은 rhwp로 PDF 렌더(검수)와 HWP↔HWPX 변환을 한다.
#
#   bash install_rhwp.sh                 # 최신 릴리스를 ~/.local/bin 에 설치
#   RHWP_VERSION=v0.8.6 bash install_rhwp.sh
#   PREFIX=/usr/local/bin bash install_rhwp.sh
#   RHWP_DOWNLOAD_BASE=https://미러/releases/download RHWP_VERSION=v0.8.6 bash install_rhwp.sh   # 내부 미러
#
# 릴리스 바이너리를 받을 수 없으면 cargo(러스트)가 있을 때 소스에서 빌드한다.
set -euo pipefail

REPO="edwardkim/rhwp"
PREFIX="${PREFIX:-$HOME/.local/bin}"
VERSION="${RHWP_VERSION:-}"

say() { printf '[rhwp] %s\n' "$*"; }
die() { printf '[rhwp] 오류: %s\n' "$*" >&2; exit 1; }

os="$(uname -s)"
arch="$(uname -m)"
case "$os" in
  Darwin) plat="macos" ;;
  Linux) plat="linux" ;;
  *) die "지원하지 않는 OS: $os (Windows는 릴리스 페이지의 zip을 받거나 한글 자동화를 쓰세요)" ;;
esac
case "$arch" in
  arm64|aarch64) cpu="aarch64" ;;
  x86_64|amd64) cpu="x86_64" ;;
  *) die "지원하지 않는 CPU: $arch" ;;
esac

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

sha256() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'
  else shasum -a 256 "$1" | awk '{print $1}'; fi
}

install_from_release() {
  command -v curl >/dev/null 2>&1 || { say "curl 이 없습니다"; return 1; }
  if [ -z "$VERSION" ]; then
    url="$(curl -fsSLI -o /dev/null -w '%{url_effective}' "https://github.com/$REPO/releases/latest" || true)"
    VERSION="${url##*/}"
    case "$VERSION" in v*) ;; *) say "최신 버전을 알아내지 못했습니다"; return 1 ;; esac
  fi
  asset="rhwp-${VERSION}-${plat}-${cpu}.tar.gz"
  base="${RHWP_DOWNLOAD_BASE:-https://github.com/$REPO/releases/download}/$VERSION"
  say "내려받는 중: $asset"
  curl -fL --retry 3 -o "$tmp/$asset" "$base/$asset" || { say "내려받기 실패: $base/$asset"; return 1; }
  if curl -fsSL -o "$tmp/SHA256SUMS.txt" "$base/SHA256SUMS.txt"; then
    want="$(grep " ${asset}\$" "$tmp/SHA256SUMS.txt" | awk '{print $1}' || true)"
    got="$(sha256 "$tmp/$asset")"
    if [ -n "$want" ] && [ "$want" != "$got" ]; then die "체크섬이 맞지 않습니다 ($asset)"; fi
    [ -n "$want" ] && say "체크섬 확인"
  fi
  tar -xzf "$tmp/$asset" -C "$tmp"
  mkdir -p "$PREFIX"
  install -m 0755 "$tmp/rhwp/rhwp" "$PREFIX/rhwp"
  if [ "$plat" = "macos" ]; then xattr -d com.apple.quarantine "$PREFIX/rhwp" 2>/dev/null || true; fi
  return 0
}

install_from_source() {
  command -v cargo >/dev/null 2>&1 || return 1
  say "소스에서 빌드합니다 (몇 분 걸림): cargo install --git https://github.com/$REPO rhwp"
  args=(install --locked --git "https://github.com/$REPO" --bin rhwp --root "$(dirname "$PREFIX")" rhwp)
  [ -n "$VERSION" ] && args+=(--tag "$VERSION")
  cargo "${args[@]}"
}

if install_from_release; then
  :
elif install_from_source; then
  :
else
  die "설치하지 못했습니다. https://github.com/$REPO/releases 에서 ${plat}-${cpu} 파일을 직접 받아 PATH에 두거나, 러스트(https://rustup.rs)를 설치한 뒤 다시 실행하세요."
fi

bin="$PREFIX/rhwp"
[ -x "$bin" ] || bin="$(command -v rhwp || true)"
[ -n "$bin" ] || die "rhwp 실행 파일을 찾지 못했습니다"
say "설치됨: $bin ($("$bin" --version 2>/dev/null | head -1))"
case ":$PATH:" in
  *":$(dirname "$bin"):"*) ;;
  *) say "PATH에 $(dirname "$bin") 가 없습니다. 셸 설정에 추가하거나 export HWPXSKILL_RHWP=\"$bin\" 를 쓰세요." ;;
esac
say "확인: python3 <스킬 폴더>/scripts/hwpx.py doctor"
