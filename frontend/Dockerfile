FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Verifica também a presença dos binários opcionais nativos do Vite/Rolldown.
# O npm pode ignorar uma falha de download dessas dependências durante o ci.
RUN npm run build

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
