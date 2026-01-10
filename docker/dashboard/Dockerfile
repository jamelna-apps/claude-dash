FROM node:20-alpine

WORKDIR /app/dashboard

# Dashboard uses only built-in Node modules, no npm install needed
COPY . .

EXPOSE 3333

CMD ["node", "server.js", "3333"]
