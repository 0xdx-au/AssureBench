FROM python:3.12-alpine@sha256:b658b05ce9c4eb97ec6fc19424818a1f31993659c2b505a532f470e83807815d

RUN apk add --no-cache docker-cli

RUN adduser -S -u 10001 -G root assurebench \
    && mkdir -p /var/lib/assurebench \
    && chown 10001:0 /var/lib/assurebench \
    && chmod 0770 /var/lib/assurebench

WORKDIR /app
COPY secassure.py server.py ./
COPY index.html app.js styles.css ./
COPY assets/brand ./assets/brand
COPY docker-entrypoint.py /usr/local/bin/docker-entrypoint.py
RUN chmod 0755 /usr/local/bin/docker-entrypoint.py

EXPOSE 8765
USER 10001:0
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 CMD ["python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/bootstrap', timeout=2)"]
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.py"]
CMD ["python3", "secassure.py", "--dashboard", "--container"]
