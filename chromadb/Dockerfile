# ChromaDB Server Dockerfile for Railway deployment
FROM chromadb/chroma:latest

# Set environment variables
ENV IS_PERSISTENT=TRUE
ENV PERSIST_DIRECTORY=/chroma/chroma
ENV ANONYMIZED_TELEMETRY=False
ENV CHROMA_SERVER_HOST=0.0.0.0
ENV CHROMA_SERVER_HTTP_PORT=8000

# Create data directory
RUN mkdir -p /chroma/chroma

# Expose the default ChromaDB port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/api/v1/heartbeat || exit 1
