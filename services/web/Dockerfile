# SENTINEL dashboard (Next.js). Deploys to Cloud Run.
# Build context = services/web.
FROM node:20-slim

WORKDIR /app
ENV NODE_ENV=production

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

ENV PORT=8080
EXPOSE 8080

# Bind to 0.0.0.0:$PORT as required by Cloud Run. At runtime, API_URL env is
# proxied by next.config rewrites (set it to the deployed API service URL).
CMD ["sh", "-c", "npm run start -- -H 0.0.0.0 -p ${PORT:-8080}"]
