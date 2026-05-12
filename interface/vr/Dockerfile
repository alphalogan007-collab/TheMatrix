FROM nginx:1.27-alpine

# Copy VR world files
COPY index.html /usr/share/nginx/html/index.html
COPY mind-bridge.js /usr/share/nginx/html/mind-bridge.js

# Nginx config — serve static files + set CORS + no cache for dev
RUN printf 'server {\n\
    listen 80;\n\
    server_name _;\n\
    root /usr/share/nginx/html;\n\
    index index.html;\n\
    gzip on;\n\
    gzip_types text/plain text/css application/javascript;\n\
    location / {\n\
        try_files $uri $uri/ /index.html;\n\
        add_header Cache-Control "no-store, no-cache, must-revalidate";\n\
        add_header Access-Control-Allow-Origin "*";\n\
        add_header Cross-Origin-Opener-Policy "same-origin";\n\
        add_header Cross-Origin-Embedder-Policy "require-corp";\n\
    }\n\
    location /health {\n\
        return 200 "ok";\n\
        add_header Content-Type text/plain;\n\
    }\n\
}\n' > /etc/nginx/conf.d/default.conf

EXPOSE 80
