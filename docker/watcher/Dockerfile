FROM node:20-alpine

# Install system dependencies for file watching
RUN apk add --no-cache bash procps lsof

WORKDIR /app/watcher

# Copy package files first for better caching
COPY package*.json ./

# Install dependencies
RUN npm ci --only=production 2>/dev/null || npm install --only=production

# Copy watcher source
COPY . .

# Entrypoint
CMD ["node", "watcher.js"]
