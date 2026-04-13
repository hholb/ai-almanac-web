FROM node:20-slim AS builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# VITE_API_URL is baked into the JS bundle at build time.
# Pass it as: docker build --build-arg VITE_API_URL=https://your-backend-url
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

FROM node:20-slim

WORKDIR /app
COPY --from=builder /app/build ./build
COPY --from=builder /app/package.json ./

EXPOSE 3000
ENV PORT=3000

CMD ["node", "build/index.js"]
