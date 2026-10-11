# Build context: repository root. Builds the frontend and serves it next to the load balancer.
FROM node:22-alpine AS frontend
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM nginx:1.27.3-alpine
COPY backend/deploy/nginx/nginx.conf /etc/nginx/nginx.conf
COPY --from=frontend /web/dist /usr/share/nginx/html
