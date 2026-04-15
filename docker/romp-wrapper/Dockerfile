FROM us-central1-docker.pkg.dev/ai-almanac/almanac/romp:latest

# Ensure google-cloud-storage is available for direct GCS downloads in the entrypoint.
RUN pip install --no-cache-dir google-cloud-storage

COPY entrypoint.sh /almanac-entrypoint.sh
RUN chmod +x /almanac-entrypoint.sh

ENTRYPOINT ["/almanac-entrypoint.sh"]
