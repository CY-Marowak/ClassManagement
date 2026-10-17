FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 CM_DEBUG=0
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY backend/ ./backend/
COPY --from=frontend /build/dist ./frontend/dist/
COPY scripts/render-start.sh ./scripts/render-start.sh
RUN useradd --uid 10001 --create-home cm
USER cm
EXPOSE 10000
CMD ["sh", "scripts/render-start.sh"]
