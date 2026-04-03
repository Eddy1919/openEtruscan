FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json* ./

RUN npm ci || npm install

COPY . .

EXPOSE 3000

ENV PORT 3000
ENV HOSTNAME "0.0.0.0"

CMD ["npm", "run", "dev"]
