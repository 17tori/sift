# Shared by the HTTP-only bootstrap and the HTTPS server blocks.
root /usr/share/nginx/html;
index index.html;

add_header X-Content-Type-Options nosniff always;
add_header Referrer-Policy strict-origin-when-cross-origin always;
add_header Cache-Control $sift_cache_control;
add_header Permissions-Policy "camera=(self), microphone=(), geolocation=()" always;
# Telegram Web embeds Mini Apps in an iframe: allow only Telegram origins as ancestors.
add_header Content-Security-Policy "default-src 'self'; script-src 'self' https://telegram.org; style-src 'self' 'unsafe-inline'; img-src * data: blob:; font-src 'self' data:; connect-src 'self'; frame-ancestors https://web.telegram.org https://*.telegram.org https://telegram.org; base-uri 'self'; form-action 'self'" always;

location = /healthz { access_log off; proxy_pass http://api_upstream/healthz; }

location = /api/v1/searches {
    limit_req zone=upload burst=5 nodelay;
    client_max_body_size 12m;
    proxy_pass http://api_upstream;
    include /etc/nginx/proxy_params.inc;
}

location /api/ {
    limit_req zone=api burst=60 nodelay;
    client_max_body_size 1m;
    proxy_pass http://api_upstream;
    include /etc/nginx/proxy_params.inc;
}

location = ${BOT_WEBHOOK_PATH} {
    client_max_body_size 1m;
    proxy_pass http://bot_upstream;
    include /etc/nginx/proxy_params.inc;
}

# No add_header inside locations: that would drop every server-level security header above.
# Cache-Control comes from the $sift_cache_control map in nginx.conf.
location /assets/ {
    try_files $uri =404;
}

location / {
    try_files $uri $uri/ /index.html;
}
