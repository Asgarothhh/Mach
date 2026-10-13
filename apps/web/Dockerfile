FROM node:22-bookworm-slim AS build
WORKDIR /src

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_DEMO_MODE=false
ARG VITE_API_BASE_URL=http://localhost:8000/api/v1
ARG VITE_LIVEKIT_URL=
ARG VITE_APP_NAME=MTS Inbound Voice Agent
ARG VITE_BACKEND_TEXT_TEST=true
ARG VITE_BACKEND_ADMIN_SESSIONS=false
ARG VITE_BACKEND_TEST_TENANT_ID=acme-it-demo

ENV VITE_DEMO_MODE=$VITE_DEMO_MODE \
    VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_LIVEKIT_URL=$VITE_LIVEKIT_URL \
    VITE_APP_NAME=$VITE_APP_NAME \
    VITE_BACKEND_TEXT_TEST=$VITE_BACKEND_TEXT_TEST \
    VITE_BACKEND_ADMIN_SESSIONS=$VITE_BACKEND_ADMIN_SESSIONS \
    VITE_BACKEND_TEST_TENANT_ID=$VITE_BACKEND_TEST_TENANT_ID

RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
