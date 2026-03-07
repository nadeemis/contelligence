# ── Stage 1: Build ──────────────────────────────────────────
FROM node:20-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# ── Stage 2: Serve ──────────────────────────────────────────
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf.template
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
ENV BACKEND_URL=http://contelligence-agent:8000
EXPOSE 80
ENTRYPOINT ["/docker-entrypoint.sh"]