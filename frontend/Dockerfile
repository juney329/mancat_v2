FROM node:18-alpine

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

COPY frontend .

ENV NEXT_TELEMETRY_DISABLED=1
ENV NEXT_PUBLIC_API_BASE=http://backend:8000

CMD ["npm", "run", "dev", "--", "-H", "0.0.0.0"]
