# Token Guard-branded Grafana. OSS has no white-labeling config, so we bake the brand in
# at build time (runs as root, no runtime permission/entrypoint hacks, reproducible).
# Pinned version because the patches target version-specific frontend-bundle assets.
FROM grafana/grafana:13.0.2

COPY branding/scopic_icon.svg /tmp/scopic_icon.svg
COPY branding/scopic_text_logo.svg /tmp/scopic_text_logo.svg
COPY branding/fav32.png /tmp/fav32.png
COPY branding/apple-touch-icon.png /tmp/apple-touch-icon.png
COPY branding/login_background_dark.svg /tmp/login_background_dark.svg
COPY branding/login_background_light.svg /tmp/login_background_light.svg

USER root
RUN set -e; cd /usr/share/grafana/public; \
    # --- app title: tab title, index.html, login text ---
    sed -i 's/AppTitle="Grafana"/AppTitle="Token Guard AI Usage Analytics"/g' build/*.js; \
    sed -i 's/\[\[\.AppTitle\]\]/Token Guard AI Usage Analytics/g' views/index.html; \
    # hide the login footer (Documentation/Support/Community/Open Source) via injected CSS
    sed -i 's#</head>#<style>footer{display:none !important;}</style></head>#' views/index.html; \
    (grep -rl "Welcome to Grafana" build/*.js 2>/dev/null | xargs -r \
       sed -i 's/Welcome to Grafana/Welcome to Token Guard/g') || true; \
    # --- logo: nav + login icon (hashed bundle asset) and the wordmark ---
    for f in build/static/img/grafana_icon.*.svg img/grafana_icon.svg img/grafana_mask_icon.svg; do \
      [ -e "$f" ] && cp /tmp/scopic_icon.svg "$f"; done; \
    for f in build/static/img/grafana_text_logo_*.svg; do \
      [ -e "$f" ] && cp /tmp/scopic_text_logo.svg "$f"; done; \
    # --- favicons (index.html links public/build/img/fav32.png — the real one) ---
    for f in img/fav32.png build/img/fav32.png build/static/img/fav32.*.png; do \
      [ -e "$f" ] && cp /tmp/fav32.png "$f"; done; \
    for f in img/apple-touch-icon.png build/img/apple-touch-icon.png build/static/img/apple-touch-icon.*.png; do \
      [ -e "$f" ] && cp /tmp/apple-touch-icon.png "$f"; done; \
    # --- Token Guard login background ---
    for f in img/login_background_dark.svg build/static/img/login_background_dark.*.svg; do \
      [ -e "$f" ] && cp /tmp/login_background_dark.svg "$f"; done; \
    for f in img/login_background_light.svg build/static/img/login_background_light.*.svg; do \
      [ -e "$f" ] && cp /tmp/login_background_light.svg "$f"; done; \
    true
USER grafana
