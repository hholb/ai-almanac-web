FROM us-central1-docker.pkg.dev/ai-almanac/almanac/romp:latest

COPY entrypoint.sh /almanac-entrypoint.sh
RUN chmod +x /almanac-entrypoint.sh

ENTRYPOINT ["/almanac-entrypoint.sh"]
