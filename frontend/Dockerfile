# Frontend Dockerfile (Vite React)
# Build stage
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* yarn.lock* pnpm-lock.yaml* .npmrc* ./
# Install deps (supports npm/yarn/pnpm). Default npm
RUN if [ -f package-lock.json ]; then npm ci; \
    elif [ -f yarn.lock ]; then yarn install --frozen-lockfile; \
    elif [ -f pnpm-lock.yaml ]; then npm i -g pnpm && pnpm i --frozen-lockfile; \
    else npm i; fi
# Copy source
COPY . .
# Optional: override the backend API URL at build time
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
# Build with Vite
RUN npm run build

# Run stage
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
# SPA routing fallback
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
